from flask import Flask, render_template, jsonify, request, session
import os
import pandas as pd
from werkzeug.utils import secure_filename
import tempfile
from nvidia_utils import process_pdf_file
import traceback
import json
import uuid
from datetime import datetime

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
app.config['UPLOAD_FOLDER'] = tempfile.gettempdir()
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
# Temporary storage for client data (in production, use Redis or database)
temp_data_storage = {}
# JSON files storage directory
JSON_STORAGE_DIR = os.path.join(os.path.dirname(__file__), 'client_data')
os.makedirs(JSON_STORAGE_DIR, exist_ok=True)

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


# Required fields for completeness check
REQUIRED_FIELDS = [
    'legal_name',
    'contact_email',
    'registered_address',
    'contact_phone'
]

# Alternative field names that can satisfy requirements
FIELD_ALIASES = {
    'contact_email': ['email', 'primary_email', 'contact_email'],
    'contact_phone': ['phone', 'contact_phone'],
    'registered_address': ['registered_address', 'operational_address', 'mailing_address', 'address'],
    'legal_name': ['legal_name', 'dba_name', 'entity_name']
}

def check_data_completeness(structured_data: dict) -> dict:
    """
    Check if structured data has all required fields.
    Returns dict with 'complete' bool and 'missing_fields' list.
    """
    missing_fields = []
    
    for required_field in REQUIRED_FIELDS:
        # Check if any alias of this field has a value
        found = False
        for alias in FIELD_ALIASES.get(required_field, [required_field]):
            value = structured_data.get(alias)
            if value is not None and value != '' and str(value).strip():
                # Check if it's an object/array that's empty
                if isinstance(value, (dict, list)):
                    if len(value) > 0:
                        found = True
                        break
                else:
                    found = True
                    break
        
        if not found:
            missing_fields.append(required_field)
    
    return {
        'complete': len(missing_fields) == 0,
        'missing_fields': missing_fields,
        'required_fields': REQUIRED_FIELDS
    }


@app.route('/api/check-completeness', methods=['POST'])
def check_completeness():
    """Check if client data is complete before validation."""
    try:
        data = request.get_json()
        if not data or 'structured_data' not in data:
            return jsonify({'error': 'No structured_data provided'}), 400
        
        structured_data = data['structured_data']
        result = check_data_completeness(structured_data)
        
        return jsonify({
            'success': True,
            **result
        })
    
    except Exception as e:
        return jsonify({
            'error': f'Completeness check failed: {str(e)}',
            'details': traceback.format_exc()
        }), 500


@app.route('/api/save-client-data', methods=['POST'])
def save_client_data():
    """Temporarily save client data JSON before validation."""
    try:
        data = request.get_json()
        if not data or 'structured_data' not in data:
            return jsonify({'error': 'No structured_data provided'}), 400
        
        # Generate unique ID for this client data
        client_data_id = str(uuid.uuid4())
        
        # Store in memory for quick access
        temp_data_storage[client_data_id] = {
            'structured_data': data['structured_data'],
            'filename': data.get('filename', 'unknown'),
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat()
        }
        
        # Also save to JSON file
        filepath = os.path.join(JSON_STORAGE_DIR, f'{client_data_id}.json')
        with open(filepath, 'w') as f:
            json.dump({
                'client_data_id': client_data_id,
                'filename': data.get('filename', 'unknown'),
                'structured_data': data['structured_data'],
                'created_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat()
            }, f, indent=2)
        
        return jsonify({
            'success': True,
            'client_data_id': client_data_id
        })
    
    except Exception as e:
        return jsonify({
            'error': f'Failed to save client data: {str(e)}',
            'details': traceback.format_exc()
        }), 500


@app.route('/api/update-client-data', methods=['POST'])
def update_client_data():
    """Update temporarily saved client data with user-provided missing fields."""
    try:
        data = request.get_json()
        if not data or 'client_data_id' not in data or 'updates' not in data:
            return jsonify({'error': 'Missing client_data_id or updates'}), 400
        
        client_data_id = data['client_data_id']
        if client_data_id not in temp_data_storage:
            return jsonify({'error': 'Client data not found'}), 404
        
        # Update the structured data with user-provided values
        updates = data['updates']
        structured_data = temp_data_storage[client_data_id]['structured_data']
        
        for field, value in updates.items():
            # Map required field names to actual field names in structured_data
            if field == 'contact_email':
                structured_data['contact_email'] = value
            elif field == 'contact_phone':
                structured_data['contact_phone'] = value
            elif field == 'registered_address':
                structured_data['registered_address'] = value
            elif field == 'legal_name':
                structured_data['legal_name'] = value
            else:
                structured_data[field] = value
        
        temp_data_storage[client_data_id]['structured_data'] = structured_data
        temp_data_storage[client_data_id]['updated_at'] = datetime.now().isoformat()
        
        # Update JSON file
        filepath = os.path.join(JSON_STORAGE_DIR, f'{client_data_id}.json')
        if os.path.exists(filepath):
            with open(filepath, 'r') as f:
                file_data = json.load(f)
            file_data['structured_data'] = structured_data
            file_data['updated_at'] = datetime.now().isoformat()
            with open(filepath, 'w') as f:
                json.dump(file_data, f, indent=2)
        
        # Check completeness again
        completeness = check_data_completeness(structured_data)
        
        return jsonify({
            'success': True,
            'complete': completeness['complete'],
            'missing_fields': completeness['missing_fields']
        })
    
    except Exception as e:
        return jsonify({
            'error': f'Failed to update client data: {str(e)}',
            'details': traceback.format_exc()
        }), 500


@app.route('/validation-handler')
def validation_handler():
    """Page to view and handle saved JSON files for validation."""
    return render_template('validation_handler.html')


@app.route('/api/list-json-files', methods=['GET'])
def list_json_files():
    """List all saved JSON files."""
    try:
        files = []
        if os.path.exists(JSON_STORAGE_DIR):
            for filename in os.listdir(JSON_STORAGE_DIR):
                if filename.endswith('.json'):
                    filepath = os.path.join(JSON_STORAGE_DIR, filename)
                    stat = os.stat(filepath)
                    files.append({
                        'filename': filename,
                        'client_data_id': filename.replace('.json', ''),
                        'created_at': datetime.fromtimestamp(stat.st_ctime).isoformat(),
                        'updated_at': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        'size': stat.st_size
                    })
        
        # Sort by updated_at descending (newest first)
        files.sort(key=lambda x: x['updated_at'], reverse=True)
        
        return jsonify({
            'success': True,
            'files': files
        })
    
    except Exception as e:
        return jsonify({
            'error': f'Failed to list files: {str(e)}',
            'details': traceback.format_exc()
        }), 500


@app.route('/api/get-json-file/<client_data_id>', methods=['GET'])
def get_json_file(client_data_id):
    """Get a specific JSON file by ID."""
    try:
        filepath = os.path.join(JSON_STORAGE_DIR, f'{client_data_id}.json')
        
        if not os.path.exists(filepath):
            return jsonify({'error': 'File not found'}), 404
        
        with open(filepath, 'r') as f:
            data = json.load(f)
        
        return jsonify({
            'success': True,
            'data': data
        })
    
    except Exception as e:
        return jsonify({
            'error': f'Failed to read file: {str(e)}',
            'details': traceback.format_exc()
        }), 500


if __name__ == "__main__":
    app.run(debug=True)

