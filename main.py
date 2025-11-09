from flask import Flask, render_template, jsonify, request
from google.cloud import storage, firestore
from google.oauth2 import service_account
from werkzeug.utils import secure_filename
import os
from datetime import datetime
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# Load credentials from the service account key file
CREDENTIALS_PATH = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS', 'service-account-key.json')

if os.path.exists(CREDENTIALS_PATH):
    credentials = service_account.Credentials.from_service_account_file(CREDENTIALS_PATH)
    storage_client = storage.Client(credentials=credentials)
    firestore_client = firestore.Client(credentials=credentials)
    print(f"✓ Successfully loaded credentials from: {CREDENTIALS_PATH}")
else:
    print(f"❌ ERROR: Credentials file not found at: {CREDENTIALS_PATH}")
    print("Please follow the setup instructions in SETUP_GUIDE.md")
    storage_client = None
    firestore_client = None

BUCKET_NAME = os.environ.get('GCS_BUCKET_NAME', 'vendor-onboarding-files-mu')
ALLOWED_EXTENSIONS = {'pdf', 'docx', 'xlsx'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

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

@app.route('/callback')
def callback():
    # Auth0 will redirect here after authentication
    # The JavaScript in login.html will handle the callback
    return render_template('login.html')

@app.route('/api/upload', methods=['POST'])
def upload_file():
    if not storage_client or not firestore_client:
        return jsonify({'error': 'Google Cloud credentials not configured. Check console.'}), 500
    
    try:
        # Get user email from Auth0 (passed from frontend)
        user_email = request.form.get('user_email')
        if not user_email:
            return jsonify({'error': 'User email is required'}), 400

        # Check if file is in request
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400

        if not allowed_file(file.filename):
            return jsonify({'error': 'Only PDF, DOCX, and XLSX files are allowed'}), 400

        # Secure the filename
        filename = secure_filename(file.filename)
        
        # Create unique filename with timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        unique_filename = f"{user_email}/{timestamp}_{filename}"

        # Upload to Google Cloud Storage
        bucket = storage_client.bucket(BUCKET_NAME)
        blob = bucket.blob(unique_filename)
        blob.upload_from_file(file)

        # Get public URL (or signed URL for private buckets)
        file_url = f"gs://{BUCKET_NAME}/{unique_filename}"

        # Save metadata to Firestore
        doc_ref = firestore_client.collection('documents').document()
        doc_ref.set({
            'user_email': user_email,
            'filename': filename,
            'storage_path': unique_filename,
            'file_url': file_url,
            'upload_date': firestore.SERVER_TIMESTAMP,
            'file_type': filename.rsplit('.', 1)[1].lower()
        })

        return jsonify({
            'message': 'File uploaded successfully',
            'filename': filename,
            'document_id': doc_ref.id
        }), 200

    except Exception as e:
        print(f"Error uploading file: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/documents/<user_email>', methods=['GET'])
def get_user_documents(user_email):
    if not firestore_client:
        return jsonify({'error': 'Google Cloud credentials not configured. Check console.'}), 500
    
    try:
        # Query Firestore for user's documents
        docs_ref = firestore_client.collection('documents')
        query = docs_ref.where('user_email', '==', user_email)
        
        documents = []
        for doc in query.stream():
            doc_data = doc.to_dict()
            doc_data['id'] = doc.id
            # Add upload_date as timestamp if it exists
            if 'upload_date' in doc_data and doc_data['upload_date']:
                doc_data['upload_date'] = doc_data['upload_date'].isoformat() if hasattr(doc_data['upload_date'], 'isoformat') else str(doc_data['upload_date'])
            documents.append(doc_data)

        documents.sort(key=lambda x: x.get('upload_date', ''), reverse=True)

        return jsonify({'documents': documents}), 200

    except Exception as e:
        print(f"Error fetching documents: {str(e)}")
        return jsonify({'error': str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True)
