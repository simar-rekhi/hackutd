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

# ---- (Sneha) Optional Google Cloud + Firestore support ----
# These imports are optional; app will still run if credentials are absent.
try:
    from google.cloud import storage, firestore
    from google.oauth2 import service_account
    GCP_AVAILABLE = True
except Exception:
    GCP_AVAILABLE = False

from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# =========================
# App Config (Gabe kept)
# =========================
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB
app.config['UPLOAD_FOLDER'] = tempfile.gettempdir()
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

# Local persistent storage for original uploads
BASE_DIR = os.path.dirname(__file__)
UPLOADS_DIR = os.path.join(BASE_DIR, 'uploads')  # stored by user_email subfolders
os.makedirs(UPLOADS_DIR, exist_ok=True)

# Temporary storage for client data (in production, use Redis or database)
temp_data_storage = {}

# JSON files storage directory (Gabe)
JSON_STORAGE_DIR = os.path.join(BASE_DIR, 'client_data')
os.makedirs(JSON_STORAGE_DIR, exist_ok=True)

# =========================
# Dataset columns (Gabe)
# =========================
DATASET_COLUMNS = None
try:
    dataset_path = os.path.join(BASE_DIR, 'topo', 'global_dataset.xlsx')
    if os.path.exists(dataset_path):
        df = pd.read_excel(dataset_path)
        DATASET_COLUMNS = list(df.columns)
except Exception as e:
    print(f"Warning: Could not load dataset columns: {e}")
    DATASET_COLUMNS = [
        'legal_name', 'dba_name', 'entity_type', 'registration_number', 'jurisdiction',
        'registered_address', 'operational_address', 'mailing_address', 'contact_name',
        'contact_role', 'contact_email', 'contact_phone', 'tax_id_number', 'vat_gst_registration',
        'bank_name', 'bank_account_number_masked', 'bank_swift_code', 'bank_routing_number',
        'credit_score', 'aml_risk_rating', 'adverse_media_screen'
    ]

# =========================
# GCP clients (Sneha, optional)
# =========================
storage_client = None
firestore_client = None
if GCP_AVAILABLE:
    CREDENTIALS_PATH = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS', 'service-account-key.json')
    if os.path.exists(CREDENTIALS_PATH):
        try:
            credentials = service_account.Credentials.from_service_account_file(CREDENTIALS_PATH)
            storage_client = storage.Client(credentials=credentials)
            firestore_database = os.environ.get('FIRESTORE_DATABASE', 'goldman-sachs-database')
            firestore_client = firestore.Client(credentials=credentials, database=firestore_database)
            print(f"✓ GCP ready. Using Firestore DB: {firestore_database}")
        except Exception as e:
            print(f"⚠️ Could not init GCP clients: {e}")
    else:
        print(f"⚠️ GOOGLE_APPLICATION_CREDENTIALS missing at: {CREDENTIALS_PATH}")

BUCKET_NAME = os.environ.get('GCS_BUCKET_NAME', '')  # leave empty to skip GCS
ALLOWED_EXTENSIONS = {'pdf', 'docx', 'xlsx'}

def allowed_file(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# =========================
# Routes (shared)
# =========================
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
    # Both Gabe & Sneha referenced 'client/dashboard.html'
    return render_template('client/dashboard.html')

# =========================
# (Gabe) PDF processing endpoints - UNCHANGED
# =========================
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

        filename = secure_filename(file.filename)
        temp_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(temp_path)

        try:
            if not DATASET_COLUMNS:
                return jsonify({'error': 'Dataset columns not loaded'}), 500

            result = process_pdf_file(temp_path, DATASET_COLUMNS)

            # cleanup
            try:
                os.remove(temp_path)
            except Exception:
                pass

            return jsonify({
                'success': True,
                'filename': result['filename'],
                'structured_data': result['structured_data'],
                'extracted_text_preview': result['extracted_text'][:500] + '...'
                    if len(result['extracted_text']) > 500 else result['extracted_text']
            })

        except Exception as e:
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

        results, errors = [], []

        for file in files:
            if file.filename == '':
                continue
            if not file.filename.lower().endswith('.pdf'):
                errors.append(f'{file.filename}: Not a PDF file')
                continue

            filename = secure_filename(file.filename)
            temp_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            try:
                file.save(temp_path)

                if not DATASET_COLUMNS:
                    results.append({'filename': filename, 'error': 'Dataset columns not loaded'})
                    continue

                result = process_pdf_file(temp_path, DATASET_COLUMNS)
                results.append({
                    'filename': result['filename'],
                    'success': True,
                    'structured_data': result['structured_data']
                })
            except Exception as e:
                errors.append(f'{file.filename}: {str(e)}')
            finally:
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

# =========================
# (Gabe) Completeness + Save/Update JSON - UNCHANGED
# =========================
REQUIRED_FIELDS = ['legal_name', 'contact_email', 'registered_address', 'contact_phone']
FIELD_ALIASES = {
    'contact_email': ['email', 'primary_email', 'contact_email'],
    'contact_phone': ['phone', 'contact_phone'],
    'registered_address': ['registered_address', 'operational_address', 'mailing_address', 'address'],
    'legal_name': ['legal_name', 'dba_name', 'entity_name']
}

def check_data_completeness(structured_data: dict) -> dict:
    missing_fields = []
    for required_field in REQUIRED_FIELDS:
        found = False
        for alias in FIELD_ALIASES.get(required_field, [required_field]):
            value = structured_data.get(alias)
            if value is not None and str(value).strip():
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
    try:
        data = request.get_json()
        if not data or 'structured_data' not in data:
            return jsonify({'error': 'No structured_data provided'}), 400
        result = check_data_completeness(data['structured_data'])
        return jsonify({'success': True, **result})
    except Exception as e:
        return jsonify({'error': f'Completeness check failed: {str(e)}',
                        'details': traceback.format_exc()}), 500

@app.route('/api/save-client-data', methods=['POST'])
def save_client_data():
    try:
        data = request.get_json()
        if not data or 'structured_data' not in data:
            return jsonify({'error': 'No structured_data provided'}), 400

        client_data_id = str(uuid.uuid4())
        temp_data_storage[client_data_id] = {
            'structured_data': data['structured_data'],
            'filename': data.get('filename', 'unknown'),
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat()
        }

        filepath = os.path.join(JSON_STORAGE_DIR, f'{client_data_id}.json')
        with open(filepath, 'w') as f:
            json.dump({
                'client_data_id': client_data_id,
                'filename': data.get('filename', 'unknown'),
                'structured_data': data['structured_data'],
                'created_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat()
            }, f, indent=2)

        return jsonify({'success': True, 'client_data_id': client_data_id})
    except Exception as e:
        return jsonify({'error': f'Failed to save client data: {str(e)}',
                        'details': traceback.format_exc()}), 500

@app.route('/api/update-client-data', methods=['POST'])
def update_client_data():
    try:
        data = request.get_json()
        if not data or 'client_data_id' not in data or 'updates' not in data:
            return jsonify({'error': 'Missing client_data_id or updates'}), 400

        client_data_id = data['client_data_id']
        if client_data_id not in temp_data_storage:
            return jsonify({'error': 'Client data not found'}), 404

        updates = data['updates']
        structured_data = temp_data_storage[client_data_id]['structured_data']

        for field, value in updates.items():
            if field in ('contact_email', 'contact_phone', 'registered_address', 'legal_name'):
                structured_data[field] = value
            else:
                structured_data[field] = value

        temp_data_storage[client_data_id]['structured_data'] = structured_data
        temp_data_storage[client_data_id]['updated_at'] = datetime.now().isoformat()

        filepath = os.path.join(JSON_STORAGE_DIR, f'{client_data_id}.json')
        if os.path.exists(filepath):
            with open(filepath, 'r') as f:
                file_data = json.load(f)
            file_data['structured_data'] = structured_data
            file_data['updated_at'] = datetime.now().isoformat()
            with open(filepath, 'w') as f:
                json.dump(file_data, f, indent=2)

        completeness = check_data_completeness(structured_data)
        return jsonify({'success': True,
                        'complete': completeness['complete'],
                        'missing_fields': completeness['missing_fields']})
    except Exception as e:
        return jsonify({'error': f'Failed to update client data: {str(e)}',
                        'details': traceback.format_exc()}), 500

# =========================
# (Gabe) Validation Handler - UNCHANGED
# =========================
@app.route('/validation-handler')
def validation_handler():
    return render_template('validation_handler.html')

@app.route('/api/list-json-files', methods=['GET'])
def list_json_files():
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
        files.sort(key=lambda x: x['updated_at'], reverse=True)
        return jsonify({'success': True, 'files': files})
    except Exception as e:
        return jsonify({'error': f'Failed to list files: {str(e)}',
                        'details': traceback.format_exc()}), 500

@app.route('/api/get-json-file/<client_data_id>', methods=['GET'])
def get_json_file(client_data_id):
    try:
        filepath = os.path.join(JSON_STORAGE_DIR, f'{client_data_id}.json')
        if not os.path.exists(filepath):
            return jsonify({'error': 'File not found'}), 404
        with open(filepath, 'r') as f:
            data = json.load(f)
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        return jsonify({'error': f'Failed to read file: {str(e)}',
                        'details': traceback.format_exc()}), 500

# =========================
# (Sneha + Local) Upload & Documents listing
# =========================
@app.route('/api/upload', methods=['POST'])
def upload_file_store_and_optional_gcs():
    """
    Stores the uploaded file locally under uploads/<user_email>/timestamp_filename.
    If GCS & Firestore are configured, also uploads to GCS and writes a Firestore doc.
    """
    try:
        # user_email is required to organize storage by account
        user_email = request.form.get('user_email')
        if not user_email:
            return jsonify({'error': 'User email is required'}), 400

        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400

        if not allowed_file(file.filename):
            return jsonify({'error': 'Only PDF, DOCX, and XLSX files are allowed'}), 400

        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        unique_filename = f"{timestamp}_{filename}"

        # ---- Local persistent save (always) ----
        user_dir = os.path.join(UPLOADS_DIR, user_email)
        os.makedirs(user_dir, exist_ok=True)
        local_path = os.path.join(user_dir, unique_filename)
        file.stream.seek(0)
        file.save(local_path)

        # ---- Optional GCS + Firestore ----
        document_id = None
        if storage_client and firestore_client and BUCKET_NAME:
            try:
                bucket = storage_client.bucket(BUCKET_NAME)
                blob = bucket.blob(f"{user_email}/{unique_filename}")
                # re-open the saved local file to upload
                with open(local_path, 'rb') as f:
                    blob.upload_from_file(f)
                file_url = f"gs://{BUCKET_NAME}/{user_email}/{unique_filename}"

                doc_ref = firestore_client.collection('documents').document()
                doc_ref.set({
                    'user_email': user_email,
                    'filename': filename,
                    'storage_path': f"{user_email}/{unique_filename}",
                    'file_url': file_url,
                    'upload_date': firestore.SERVER_TIMESTAMP,
                    'file_type': filename.rsplit('.', 1)[1].lower()
                })
                document_id = doc_ref.id
            except Exception as e:
                # Don't fail the whole request if GCS/Firestore fail; local save already happened.
                print(f"⚠️ GCS/Firestore error (continuing with local save): {e}")

        return jsonify({
            'message': 'File stored successfully',
            'filename': filename,
            'document_id': document_id
        }), 200

    except Exception as e:
        print(f"Error uploading file: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/documents/<user_email>', methods=['GET'])
def get_user_documents(user_email):
    """
    If Firestore available, return docs from Firestore (newest first).
    Otherwise, list locally stored uploads for that user.
    """
    try:
        # Prefer Firestore if configured
        if firestore_client:
            docs_ref = firestore_client.collection('documents')
            query = docs_ref.where('user_email', '==', user_email).order_by('upload_date', direction=firestore.Query.DESCENDING)
            documents = []
            for doc in query.stream():
                d = doc.to_dict()
                d['id'] = doc.id
                # Normalize upload_date for frontend
                if 'upload_date' in d and d['upload_date'] and hasattr(d['upload_date'], 'timestamp'):
                    d['upload_date'] = {'_seconds': int(d['upload_date'].timestamp())}
                else:
                    d['upload_date'] = None
                documents.append(d)
            return jsonify({'documents': documents}), 200

        # Fallback: local listing
        user_dir = os.path.join(UPLOADS_DIR, user_email)
        documents = []
        if os.path.exists(user_dir):
            for name in sorted(os.listdir(user_dir), reverse=True):
                path = os.path.join(user_dir, name)
                if os.path.isfile(path):
                    stat = os.stat(path)
                    # mimic Firestore date shape {_seconds: ...}
                    documents.append({
                        'id': None,
                        'user_email': user_email,
                        'filename': name.split('_', 1)[-1] if '_' in name else name,
                        'storage_path': f'local://{user_email}/{name}',
                        'file_url': None,
                        'upload_date': {'_seconds': int(stat.st_mtime)},
                        'file_type': name.rsplit('.', 1)[-1].lower() if '.' in name else ''
                    })
        return jsonify({'documents': documents}), 200

    except Exception as e:
        print(f"Error fetching documents: {str(e)}")
        return jsonify({'error': str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True)
