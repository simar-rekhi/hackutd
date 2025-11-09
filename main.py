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
import glob

# ---- (Sneha) Optional Google Cloud + Firestore support ----
# These imports are optional; app will still run if credentials are absent.
try:
    from google.cloud import storage, firestore
    from google.oauth2 import service_account
    GCP_AVAILABLE = True
except Exception:
    GCP_AVAILABLE = False

# =========================
# Flask setup
# =========================
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOADS_DIR = os.path.join(BASE_DIR, 'uploads')
JSON_STORAGE_DIR = os.path.join(BASE_DIR, 'client_data')
TEMPLATES_DIR = os.path.join(BASE_DIR, 'templates')

os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(JSON_STORAGE_DIR, exist_ok=True)

# Where to cache temp uploads before processing (Gabe-style)
app.config['UPLOAD_FOLDER'] = tempfile.gettempdir()

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
            firestore_client = firestore.Client(credentials=credentials, project=credentials.project_id)
        except Exception as e:
            print(f"Warning: could not initialize GCP clients: {e}")
            storage_client = None
            firestore_client = None
    else:
        storage_client = None
        firestore_client = None

BUCKET_NAME = os.environ.get('GCS_BUCKET_NAME')  # optional; only used if GCP clients are configured

# =========================
# Routes (views)
# =========================
@app.route('/')
def home():
    return render_template('Home.html')

@app.route('/login')
def login():
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    # Both Gabe & Sneha referenced 'client/dashboard.html'
    return render_template('client/dashboard.html')

@app.route('/validation-handler')
def validation_handler():
    return render_template('validation_handler.html')

@app.route('/employee-dashboard')
def employee_dashboard():
    # Employee view (Goldman Sachs reviewers)
    return render_template('server/employee_dashboard.html')

# =========================
# (Gabe) PDF processing endpoints - UNCHANGED IN BEHAVIOR
# =========================
@app.route('/api/process-pdf', methods=['POST'])
def process_pdf():
    """
    Uploads a PDF, runs OCR/ML parsing (via nvidia_utils.process_pdf_file),
    stores structured JSON under client_data/, and returns processing result.
    """
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

        # Run your ML/Nemotron/Gemini OCR pipeline (Gabe)
        result = process_pdf_file(temp_path)

        # Build client_data payload
        client_data_id = result.get('client_data_id') or str(uuid.uuid4())
        structured = result.get('structured_data') or {}

        # Persist JSON locally (always)
        out = {
            'client_data_id': client_data_id,
            'filename': filename,
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat(),
            'structured_data': structured
        }
        json_path = os.path.join(JSON_STORAGE_DIR, f'{client_data_id}.json')
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(out, f, indent=2)

        # Clean temp
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except Exception:
            pass

        return jsonify({
            'success': True,
            'filename': filename,
            'client_data_id': client_data_id,
            'structured_data': structured
        }), 200

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
    return {'complete': len(missing_fields) == 0, 'missing_fields': missing_fields}

# temporary cache in memory while form is open
temp_data_storage = {}

@app.route('/api/update-client-data', methods=['POST'])
def update_client_data():
    """
    Gabe: Accepts updates for missing fields from dashboard modal
    and merges them into the stored JSON under client_data/.
    """
    try:
        data = request.get_json(force=True)
        client_data_id = data.get('client_data_id')
        update = data.get('update', {})

        if not client_data_id:
            return jsonify({'error': 'client_data_id is required'}), 400

        # read existing JSON
        filepath = os.path.join(JSON_STORAGE_DIR, f'{client_data_id}.json')
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                file_data = json.load(f)
        else:
            # create shell if not found
            file_data = {
                'client_data_id': client_data_id,
                'filename': None,
                'created_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat(),
                'structured_data': {}
            }

        structured_data = file_data.get('structured_data', {})
        # merge update (overwrites)
        for field, value in update.items():
            structured_data[field] = value

        file_data['structured_data'] = structured_data
        file_data['updated_at'] = datetime.now().isoformat()

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(file_data, f, indent=2)

        completeness = check_data_completeness(structured_data)
        return jsonify({'success': True,
                        'complete': completeness['complete'],
                        'missing_fields': completeness['missing_fields']})
    except Exception as e:
        return jsonify({'error': f'Failed to update client data: {str(e)}',
                        'details': traceback.format_exc()}), 500

# =========================
# (Sneha) Store original uploads per account (local + optional GCS/Firestore)
# =========================
@app.route('/api/upload-original', methods=['POST'])
def upload_original():
    """
    Saves the original uploaded file into /uploads/<user_email> locally.
    If GCS/Firestore are configured, also uploads to the configured bucket and
    writes a Firestore record. Returns 200 even if cloud upload fails (local is source of truth).
    """
    try:
        user_email = request.form.get('user_email')
        file = request.files.get('file')

        if not user_email or not file:
            return jsonify({'error': 'user_email and file are required'}), 400

        filename = secure_filename(file.filename)
        unique_filename = f"{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}-{filename}"

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
                # keep local success; return note about cloud failure
                print(f"GCS/Firestore upload failed: {e}")

        return jsonify({
            'success': True,
            'filename': filename,
            'local_path': f'local://{user_email}/{unique_filename}',
            'document_id': document_id
        }), 200

    except Exception as e:
        return jsonify({'error': str(e), 'details': traceback.format_exc()}), 500

# =========================
# (Sneha) List documents for a user (local first; cloud optional)
# =========================
@app.route('/api/documents/<path:user_email>', methods=['GET'])
def list_documents(user_email):
    """
    Returns a combined (best effort) view of user's uploaded documents.
    Always scans local /uploads first; if Firestore available, appends cloud docs.
    """
    try:
        documents = []

        # Local
        local_dir = os.path.join(UPLOADS_DIR, user_email)
        if os.path.isdir(local_dir):
            for name in sorted(os.listdir(local_dir)):
                full_path = os.path.join(local_dir, name)
                if os.path.isfile(full_path):
                    stat = os.stat(full_path)
                    documents.append({
                        'user_email': user_email,
                        'filename': name,
                        'storage_path': f'local://{user_email}/{name}',
                        'file_url': None,
                        'upload_date': {'_seconds': int(stat.st_mtime)},
                        'file_type': name.rsplit('.', 1)[-1].lower() if '.' in name else ''
                    })

        # Firestore (optional)
        if firestore_client:
            try:
                q = (firestore_client.collection('documents')
                     .where('user_email', '==', user_email))
                for doc in q.stream():
                    documents.append(doc.to_dict())
            except Exception as e:
                print(f"Firestore list error: {e}")

        return jsonify({'documents': documents}), 200

    except Exception as e:
        print(f"Error fetching documents: {str(e)}")
        return jsonify({'error': str(e)}), 500

# =========================
# Employee review APIs (new)
# =========================
EMP_REQUIRED_FIELDS = [
    # Business validation required fields (tweak as your policy evolves)
    "legal_name",
    "registration_number",
    "entity_type",
    "registered_address",
    "contact_name",
    "contact_email",
    "contact_phone",
    "tax_id_number",
    "w9_w8_form_type",
    "proof_of_address",
    "source_of_funds",
]

def _safe_load(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None

def _summarize_client(obj, filename):
    client_id = obj.get("client_data_id") or os.path.splitext(filename)[0]
    structured = obj.get("structured_data") or {}

    present = [f for f in EMP_REQUIRED_FIELDS if structured.get(f)]
    missing = [f for f in EMP_REQUIRED_FIELDS if not structured.get(f)]
    total = len(EMP_REQUIRED_FIELDS) or 1
    completeness_pct = round((len(present) / total) * 100, 1)

    filled = sum(1 for v in structured.values() if v not in (None, "", []))
    total_keys = len(structured)

    return {
        "client_data_id": client_id,
        "filename": filename,
        "created_at": obj.get("created_at"),
        "updated_at": obj.get("updated_at"),
        "required_present": len(present),
        "required_total": total,
        "required_missing": missing,
        "completeness_pct": completeness_pct,
        "filled_fields": filled,
        "total_fields": total_keys,
        "preview": {
            "legal_name": structured.get("legal_name"),
            "registration_number": structured.get("registration_number"),
            "contact_email": structured.get("contact_email"),
            "contact_name": structured.get("contact_name"),
            "entity_type": structured.get("entity_type"),
        }
    }

@app.route('/api/clients')
def api_list_clients():
    if not os.path.isdir(JSON_STORAGE_DIR):
        return jsonify({"documents": [], "count": 0})
    items = []
    for path in glob.glob(os.path.join(JSON_STORAGE_DIR, "*.json")):
        filename = os.path.basename(path)
        obj = _safe_load(path)
        if not obj:
            continue
        items.append(_summarize_client(obj, filename))
    # Least complete first
    items.sort(key=lambda x: (x["required_present"], x["filled_fields"]))
    return jsonify({"documents": items, "count": len(items)})

@app.route('/api/clients/<client_id>')
def api_get_client(client_id):
    if not os.path.isdir(JSON_STORAGE_DIR):
        return jsonify({"error": "client_data folder not found"}), 404

    # Try exact filename first
    path = os.path.join(JSON_STORAGE_DIR, f"{client_id}.json")
    candidate_paths = [path] if os.path.exists(path) else glob.glob(os.path.join(JSON_STORAGE_DIR, "*.json"))

    for p in candidate_paths:
        obj = _safe_load(p)
        if not obj:
            continue
        if obj.get("client_data_id") == client_id or os.path.splitext(os.path.basename(p))[0] == client_id:
            filename = os.path.basename(p)
            summary = _summarize_client(obj, filename)
            return jsonify({"summary": summary, "raw": obj})

    return jsonify({"error": "client not found"}), 404

# =========================
# Run
# =========================
if __name__ == "__main__":
    app.run(debug=True)
