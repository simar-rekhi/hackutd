# main.py — Preserve Gabe's ML behavior; add per-user local storage (Sneha-style)
# -----------------------------------------------------------------------------
# Endpoints preserved (same paths, same response shapes as Gabe):
#   POST /api/upload-pdf            -> single PDF, runs ML, returns Gabe-like result
#   POST /api/process-multiple-pdfs -> batch PDFs, runs ML per file, returns list
#
# New behavior (side-effect only):
#   - Every uploaded PDF is ALSO copied to uploads/<user_email>/<timestamp>_<name>.pdf
#   - Does NOT change the JSON structure returned by ML
# -----------------------------------------------------------------------------

from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
from werkzeug.utils import secure_filename
from datetime import datetime
import os
import pandas as pd
import tempfile
import traceback
import shutil

# === Keep Gabe's ML import exactly ===
# Ensure this module exists in your project as it did in Gabe's setup.
from nvidia_utils import process_pdf_file

app = Flask(__name__)
CORS(app)

# -----------------------------------------------------------------------------
# Config
# -----------------------------------------------------------------------------
app.config['MAX_CONTENT_LENGTH'] = 64 * 1024 * 1024  # up to 64 MB
app.config['UPLOAD_FOLDER'] = tempfile.gettempdir()
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

# Per-user local storage base (Sneha-style)
UPLOAD_BASE_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_BASE_DIR, exist_ok=True)

# Optional dataset columns (Gabe often loads an .xlsx). If your ML ignores it, it's harmless.
DATASET_COLUMNS = None
try:
    dataset_path = os.path.join(os.path.dirname(__file__), 'topo', 'global_dataset.xlsx')
    if os.path.exists(dataset_path):
        df = pd.read_excel(dataset_path)
        DATASET_COLUMNS = list(df.columns)
    else:
        # sensible fallback (won’t interfere if your ML ignores it)
        DATASET_COLUMNS = [
            'legal_name', 'dba_name', 'entity_type', 'registration_number', 'jurisdiction',
            'registered_address', 'operational_address', 'mailing_address', 'contact_name',
            'contact_role', 'contact_email', 'contact_phone', 'tax_id_number',
            'vat_gst_registration', 'bank_name', 'bank_account_number_masked',
            'bank_swift_code', 'bank_routing_number', 'credit_score',
            'aml_risk_rating', 'adverse_media_screen'
        ]
except Exception as e:
    app.logger.warning(f"Could not load dataset columns: {e}")
    DATASET_COLUMNS = None

# -----------------------------------------------------------------------------
# Helpers (Sneha-style per-user local folder)
# -----------------------------------------------------------------------------
def _ensure_user_dir(user_email: str) -> str:
    safe_user = secure_filename(user_email or "unknown@local") or "unknown_local"
    user_dir = os.path.join(UPLOAD_BASE_DIR, safe_user)
    os.makedirs(user_dir, exist_ok=True)
    return user_dir

def _copy_to_user_folder(tmp_path: str, user_email: str, original_filename: str) -> str:
    """Copy the uploaded tmp file to uploads/<user>/<timestamp>_<original>."""
    user_dir = _ensure_user_dir(user_email)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest_name = f"{ts}_{secure_filename(original_filename)}"
    dest_path = os.path.join(user_dir, dest_name)
    shutil.copyfile(tmp_path, dest_path)
    return dest_path

# -----------------------------------------------------------------------------
# Basic routes (kept for compatibility with existing templates)
# -----------------------------------------------------------------------------
@app.route('/')
def home():
    # If you have templates/Home.html in your project, Flask will render it.
    # Otherwise, we return a simple OK so the app still runs out-of-the-box.
    try:
        return render_template('Home.html')
    except Exception:
        return "OK"

@app.route('/index')
def index():
    try:
        return render_template('Home.html')
    except Exception:
        return "OK"

@app.route('/login')
def login():
    try:
        return render_template('login.html')
    except Exception:
        return "Login OK"

@app.route('/dashboard')
def dashboard():
    # Serve the merged dashboard if you place it under templates/client/dashboard.html
    try:
        return render_template('client/dashboard.html')
    except Exception:
        return "Dashboard OK"

# -----------------------------------------------------------------------------
# Single PDF → ML (Gabe)
# Same endpoint and response fields that Gabe used. :contentReference[oaicite:1]{index=1}
# -----------------------------------------------------------------------------
@app.route('/api/upload-pdf', methods=['POST'])
def upload_pdf():
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400

        file = request.files['file']
        if not file or file.filename == '':
            return jsonify({'error': 'No file selected'}), 400

        if not (file.filename.lower().endswith('.pdf') or file.mimetype == 'application/pdf'):
            return jsonify({'error': 'Only PDF files are allowed'}), 400

        # Get email from client (Auth0); safe default keeps Gabe behavior
        user_email = request.form.get('user_email', 'unknown@local')

        # Save to temp (Gabe pattern)
        filename = secure_filename(file.filename)
        temp_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(temp_path)

        try:
            # Process via ML (same call style Gabe used)
            if DATASET_COLUMNS is None:
                result = process_pdf_file(temp_path)
            else:
                try:
                    result = process_pdf_file(temp_path, DATASET_COLUMNS)
                except TypeError:
                    result = process_pdf_file(temp_path)

            # Side-effect: copy to per-user local folder; do NOT alter response JSON
            try:
                _copy_to_user_folder(temp_path, user_email, file.filename)
            except Exception as copy_err:
                app.logger.warning(f"Local copy failed for {file.filename}: {copy_err}")

            # Clean up temp
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except Exception:
                pass

            # Return the same shape that Gabe returned: filename, structured_data, preview text. :contentReference[oaicite:2]{index=2}
            extracted = (result.get('extracted_text') or '')
            preview = extracted[:500] + '.' if len(extracted) > 500 else extracted
            return jsonify({
                'success': True,
                'filename': result.get('filename', filename),
                'structured_data': result.get('structured_data', {}),
                'extracted_text_preview': preview
            })

        except Exception as e:
            # Clean up temp file on error
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise e

    except Exception as e:
        app.logger.error("Upload/ML failed", exc_info=True)
        return jsonify({
            'error': f'Processing failed: {e}',
            'details': traceback.format_exc()
        }), 500

# -----------------------------------------------------------------------------
# Multiple PDFs → ML (Gabe)
# Same endpoint and response gist that Gabe used (results[], errors[], totals). :contentReference[oaicite:3]{index=3}
# -----------------------------------------------------------------------------
@app.route('/api/process-multiple-pdfs', methods=['POST'])
def process_multiple_pdfs():
    try:
        if 'files' not in request.files:
            return jsonify({'error': 'No files provided'}), 400

        files = request.files.getlist('files')
        if not files:
            return jsonify({'error': 'No files selected'}), 400

        user_email = request.form.get('user_email', 'unknown@local')

        results = []
        errors = []

        for f in files:
            if not f or f.filename == '':
                continue
            if not (f.filename.lower().endswith('.pdf') or f.mimetype == 'application/pdf'):
                errors.append(f'{f.filename}: Not a PDF file')
                continue

            filename = secure_filename(f.filename)
            temp_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)

            try:
                f.save(temp_path)

                # ML call (preserve Gabe behavior)
                if DATASET_COLUMNS is None:
                    r = process_pdf_file(temp_path)
                else:
                    try:
                        r = process_pdf_file(temp_path, DATASET_COLUMNS)
                    except TypeError:
                        r = process_pdf_file(temp_path)

                # Side-effect: local copy per user
                try:
                    _copy_to_user_folder(temp_path, user_email, f.filename)
                except Exception as copy_err:
                    app.logger.warning(f"Local copy failed for {f.filename}: {copy_err}")

                # Append Gabe-like per-file entry (filename + structured_data + success)
                results.append({
                    'filename': r.get('filename', filename),
                    'success': True,
                    'structured_data': r.get('structured_data', {})
                })

            except Exception as fe:
                errors.append(f'{f.filename}: {str(fe)}')
            finally:
                try:
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
                except Exception:
                    pass

        return jsonify({
            'success': True,
            'results': results,
            'errors': errors,
            'total_processed': len(results),
            'total_errors': len(errors)
        })

    except Exception as e:
        app.logger.error("Batch processing failed", exc_info=True)
        return jsonify({
            'error': f'Processing failed: {str(e)}',
            'details': traceback.format_exc()
        }), 500

# -----------------------------------------------------------------------------
# Run
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    # Debug True for dev; switch off in production.
    app.run(host="0.0.0.0", port=5000, debug=True)
