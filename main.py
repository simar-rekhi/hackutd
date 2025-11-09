from flask import Flask, render_template, jsonify, request
from werkzeug.utils import secure_filename
import os
from datetime import datetime
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

ALLOWED_EXTENSIONS = {'pdf', 'docx', 'xlsx'}

# Base upload directory
UPLOAD_BASE_DIR = 'static/uploads'

# In-memory storage for document metadata
# Structure: {user_email: [list of documents]}
documents_storage = {}

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
        
        # Create unique document ID
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        document_id = f"{user_email}_{timestamp}_{filename}".replace(' ', '_').replace('/', '_')
        
        # Ensure base upload directory exists
        if not os.path.exists(UPLOAD_BASE_DIR):
            os.makedirs(UPLOAD_BASE_DIR)
            print(f"Created base upload directory: {UPLOAD_BASE_DIR}")
        
        # Create user-specific directory (sanitize email for filesystem)
        safe_user_email = secure_filename(user_email.replace('@', '_at_').replace('.', '_'))
        user_upload_dir = os.path.join(UPLOAD_BASE_DIR, safe_user_email)
        
        # Create user directory if it doesn't exist
        if not os.path.exists(user_upload_dir):
            os.makedirs(user_upload_dir)
            print(f"Created user upload directory: {user_upload_dir}")
        
        # Create unique filename with timestamp to avoid overwrites
        unique_filename = f"{timestamp}_{filename}"
        file_path = os.path.join(user_upload_dir, unique_filename)
        
        # Save the file to local directory
        file.save(file_path)
        print(f"File saved to: {file_path}")
        
        # Store document metadata in memory
        upload_date = datetime.now()
        document_data = {
            'id': document_id,
            'user_email': user_email,
            'filename': filename,
            'upload_date': upload_date.isoformat(),
            'file_type': filename.rsplit('.', 1)[1].lower() if '.' in filename else '',
            'file_path': file_path,
            'unique_filename': unique_filename
        }
        
        # Initialize user's document list if it doesn't exist
        if user_email not in documents_storage:
            documents_storage[user_email] = []
        
        # Add document to user's list
        documents_storage[user_email].append(document_data)

        return jsonify({
            'message': 'File uploaded successfully',
            'filename': filename,
            'document_id': document_id
        }), 200

    except Exception as e:
        print(f"Error uploading file: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/documents/<user_email>', methods=['GET'])
def get_user_documents(user_email):
    try:
        # Get documents for this user from in-memory storage
        documents = documents_storage.get(user_email, [])
        
        # Sort by upload date (most recent first)
        documents.sort(key=lambda x: x.get('upload_date', ''), reverse=True)
        
        # Format documents for frontend (convert ISO date to Firestore-like format)
        formatted_documents = []
        for doc in documents:
            formatted_doc = doc.copy()
            # Convert ISO date string to timestamp format expected by frontend
            if 'upload_date' in formatted_doc:
                try:
                    date_obj = datetime.fromisoformat(formatted_doc['upload_date'])
                    # Frontend expects Firestore timestamp format with _seconds
                    formatted_doc['upload_date'] = {
                        '_seconds': int(date_obj.timestamp())
                    }
                except:
                    formatted_doc['upload_date'] = None
            formatted_documents.append(formatted_doc)

        return jsonify({'documents': formatted_documents}), 200

    except Exception as e:
        print(f"Error fetching documents: {str(e)}")
        return jsonify({'error': str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True)
