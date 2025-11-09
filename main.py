from flask import Flask, render_template, jsonify, request
import os
import pandas as pd
from werkzeug.utils import secure_filename
import tempfile
from nvidia_utils import process_pdf_file
import traceback

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
app.config['UPLOAD_FOLDER'] = tempfile.gettempdir()

# Get dataset columns for structuring
DATASET_COLUMNS = None
try:
    dataset_path = os.path.join(os.path.dirname(__file__), 'topo', 'global_dataset.xlsx')
    if os.path.exists(dataset_path):
        df = pd.read_excel(dataset_path)
        DATASET_COLUMNS = list(df.columns)
except Exception as e:
    print(f"Warning: Could not load dataset columns: {e}")
    # Fallback columns
    DATASET_COLUMNS = [
        'legal_name', 'dba_name', 'entity_type', 'registration_number', 'jurisdiction',
        'registered_address', 'operational_address', 'mailing_address', 'contact_name',
        'contact_role', 'contact_email', 'contact_phone', 'tax_id_number', 'vat_gst_registration',
        'bank_name', 'bank_account_number_masked', 'bank_swift_code', 'bank_routing_number',
        'credit_score', 'aml_risk_rating', 'adverse_media_screen'
    ]


@app.route('/')
def home():
    return render_template('Home.html')

@app.route('/index')
def index():
    return render_template('Home.html')

@app.route('/login')
def login():
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    return render_template('client/dashboard.html')


@app.route('/api/upload-pdf', methods=['POST'])
def upload_pdf():
    """Handle PDF upload and process with Gemini OCR + structuring."""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        if not file.filename.lower().endswith('.pdf'):
            return jsonify({'error': 'Only PDF files are allowed'}), 400
        
        # Save uploaded file temporarily
        filename = secure_filename(file.filename)
        temp_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(temp_path)
        
        try:
            # Process PDF with Gemini
            if not DATASET_COLUMNS:
                return jsonify({'error': 'Dataset columns not loaded'}), 500
            
            result = process_pdf_file(temp_path, DATASET_COLUMNS)
            
            # Clean up temp file
            os.remove(temp_path)
            
            return jsonify({
                'success': True,
                'filename': result['filename'],
                'structured_data': result['structured_data'],
                'extracted_text_preview': result['extracted_text'][:500] + '...' if len(result['extracted_text']) > 500 else result['extracted_text']
            })
        
        except Exception as e:
            # Clean up temp file on error
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise e
    
    except Exception as e:
        error_msg = str(e)
        traceback.print_exc()
        return jsonify({
            'error': f'Processing failed: {error_msg}',
            'details': traceback.format_exc()
        }), 500


@app.route('/api/process-multiple-pdfs', methods=['POST'])
def process_multiple_pdfs():
    """Handle multiple PDF uploads."""
    try:
        if 'files' not in request.files:
            return jsonify({'error': 'No files provided'}), 400
        
        files = request.files.getlist('files')
        if not files:
            return jsonify({'error': 'No files selected'}), 400
        
        results = []
        errors = []
        
        for file in files:
            if file.filename == '':
                continue
            
            if not file.filename.lower().endswith('.pdf'):
                errors.append(f'{file.filename}: Not a PDF file')
                continue
            
            try:
                # Save uploaded file temporarily
                filename = secure_filename(file.filename)
                temp_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(temp_path)
                
                try:
                    # Process PDF with Gemini
                    if not DATASET_COLUMNS:
                        results.append({
                            'filename': filename,
                            'error': 'Dataset columns not loaded'
                        })
                        continue
                    
                    result = process_pdf_file(temp_path, DATASET_COLUMNS)
                    results.append({
                        'filename': result['filename'],
                        'success': True,
                        'structured_data': result['structured_data']
                    })
                
                finally:
                    # Clean up temp file
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
            
            except Exception as e:
                errors.append(f'{file.filename}: {str(e)}')
                if os.path.exists(temp_path):
                    os.remove(temp_path)
        
        return jsonify({
            'success': True,
            'results': results,
            'errors': errors,
            'total_processed': len(results),
            'total_errors': len(errors)
        })
    
    except Exception as e:
        return jsonify({
            'error': f'Processing failed: {str(e)}',
            'details': traceback.format_exc()
        }), 500


if __name__ == "__main__":
    app.run(debug=True)

