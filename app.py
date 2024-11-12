from flask import Flask, render_template, request, send_file, redirect, url_for, flash, session
import pandas as pd
import os
import logging
from werkzeug.utils import secure_filename
from filelock import FileLock
import time
from datetime import datetime
import shutil

# Add to existing configuration
FILE_LOCK_TIMEOUT = 30  # seconds
FILE_RETENTION_PERIOD = 36000  # 10 hours in seconds
LOCK_DIR = 'locks'
os.makedirs(LOCK_DIR, exist_ok=True)

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'  # Required for flash messages and session

# Configuration
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'csv'}
REQUIRED_COLUMNS = ["word", "number", "old_definition", "translation", 
                   "definition", "example_sentences", "part_of_speech", "collocations"]

# Create uploads directory if it doesn't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def get_lock_path(filepath):
    """Generate a lock file path for a given file"""
    filename = os.path.basename(filepath)
    return os.path.join(LOCK_DIR, f"{filename}.lock")

def cleanup_old_files():
    """Remove files older than retention period"""
    current_time = time.time()
    for filename in os.listdir(UPLOAD_FOLDER):
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        try:
            if os.path.isfile(filepath):
                if current_time - os.path.getmtime(filepath) > FILE_RETENTION_PERIOD:
                    os.remove(filepath)
                    lock_path = get_lock_path(filepath)
                    if os.path.exists(lock_path):
                        os.remove(lock_path)
        except Exception as e:
            logger.error(f"Error cleaning up file {filepath}: {e}")

def safe_file_operation(filepath, operation_func, *args, **kwargs):
    """Safely perform file operations with locking"""
    lock_path = get_lock_path(filepath)
    try:
        with FileLock(lock_path, timeout=FILE_LOCK_TIMEOUT):
            return operation_func(*args, **kwargs)
    except TimeoutError:
        logger.error(f"Timeout waiting for file lock: {filepath}")
        raise Exception("File is currently in use. Please try again in a moment.")

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def load_dataframe():
    """Load DataFrame from session data and group by word"""
    if 'csv_file_path' in session and os.path.exists(session['csv_file_path']):
        try:
            def read_and_group():
                df = pd.read_csv(session['csv_file_path'])
                grouped = df.groupby('word', group_keys=False).apply(
                    lambda x: x.to_dict(orient='records')).to_dict()
                return grouped
            
            return safe_file_operation(session['csv_file_path'], read_and_group)
        except Exception as e:
            logger.error(f"Error loading DataFrame: {e}")
            if 'csv_file_path' in session:
                del session['csv_file_path']  # Clear invalid file path from session
    return None

@app.route('/', methods=['GET'])
def index():
    try:
        grouped_data = load_dataframe()
        current_index = session.get('current_index', 0)

        if grouped_data is not None:
            words = list(grouped_data.keys())
            current_word = words[current_index]
            entries = grouped_data[current_word]

            logger.debug(f"Data for word '{current_word}' loaded. Number of entries: {len(entries)}")

            return render_template(
                "index.html", 
                entries=entries, 
                total_words=len(words), 
                current_word_index=current_index + 1
            )
        else:
            logger.debug("No DataFrame available")
            return render_template("index.html", entries=None)
                
    except Exception as e:
        logger.error(f"Error in index route: {e}")
        flash(f"Error loading data: {str(e)}", "error")
        return render_template("index.html", entries=None)

@app.route('/load_csv', methods=['POST'])
def load_csv():
    try:
        # Clean up old files first
        cleanup_old_files()
        
        if 'csv_file' not in request.files:
            logger.warning("No file in request")
            flash('No file uploaded', 'error')
            return redirect(url_for('index'))
        
        file = request.files['csv_file']
        if file.filename == '':
            logger.warning("Empty filename")
            flash('No file selected', 'error')
            return redirect(url_for('index'))
        
        if file and allowed_file(file.filename):
            try:
                # Generate unique filename using timestamp
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f"{timestamp}_{secure_filename(file.filename)}"
                filepath = os.path.join(UPLOAD_FOLDER, filename)
                
                # Remove old file if exists in session
                if 'csv_file_path' in session and os.path.exists(session['csv_file_path']):
                    old_filepath = session['csv_file_path']
                    old_lock_path = get_lock_path(old_filepath)
                    try:
                        os.remove(old_filepath)
                        if os.path.exists(old_lock_path):
                            os.remove(old_lock_path)
                    except Exception as e:
                        logger.error(f"Error removing old file: {e}")
                
                # Save new file
                file.save(filepath)
                logger.debug(f"File saved to {filepath}")
                
                # Verify file with lock
                def verify_csv():
                    temp_df = pd.read_csv(filepath)
                    missing_columns = [col for col in REQUIRED_COLUMNS if col not in temp_df.columns]
                    if missing_columns:
                        raise ValueError(f"Missing required columns: {', '.join(missing_columns)}")
                    return temp_df
                
                safe_file_operation(filepath, verify_csv)
                
                # Update session
                session['csv_file_path'] = filepath
                session['current_index'] = 0
                
                flash('CSV file loaded successfully!', 'success')
                logger.debug("CSV processing completed successfully")
                
            except Exception as e:
                logger.error(f"Error processing CSV: {e}")
                if os.path.exists(filepath):
                    try:
                        os.remove(filepath)
                        lock_path = get_lock_path(filepath)
                        if os.path.exists(lock_path):
                            os.remove(lock_path)
                    except Exception as delete_error:
                        logger.error(f"Error cleaning up after failed upload: {delete_error}")
                flash(f"Error processing CSV file: {str(e)}", 'error')
                return redirect(url_for('index'))
        else:
            logger.warning("Invalid file type")
            flash('Invalid file type. Please upload a CSV file.', 'error')
        
        return redirect(url_for('index'))
    
    except Exception as e:
        logger.error(f"Unexpected error in load_csv: {e}")
        flash(f"An unexpected error occurred: {str(e)}", 'error')
        return redirect(url_for('index'))

@app.route('/handle_submit', methods=['POST'])
def handle_submit():
    try:
        grouped_data = load_dataframe()
        if grouped_data is None:
            flash('No CSV file loaded', 'error')
            return redirect(url_for('index'))
        
        current_index = session.get('current_index', 0)
        action = request.form.get('action')
        logger.debug(f"Handle submit action: {action}")
        
        words = list(grouped_data.keys())
        current_word = words[current_index]
        entries = grouped_data[current_word]

        # Save current entries if action is 'save', 'next', 'prev', or 'download'
        if action in ['save', 'next', 'prev', 'download']:
            def save_changes():
                for i, entry in enumerate(entries):
                    for column in REQUIRED_COLUMNS:
                        if column in ['word', 'number']:
                            continue  # Skip read-only fields
                        
                        if column in ['collocations', 'example_sentences']:
                            values = request.form.getlist(f"{column}_{i}")
                            filtered_values = [v.strip() for v in values if v.strip()]
                            cleaned_data = ' / '.join(filtered_values)
                        else:
                            form_data = request.form.get(f"{column}_{i}", '')
                            cleaned_data = form_data.strip()
                        
                        entry[column] = cleaned_data
                
                # Convert the updated grouped data back to a DataFrame
                updated_df = pd.DataFrame([entry for entries in grouped_data.values() for entry in entries])
                updated_df.to_csv(session['csv_file_path'], index=False)
                return True

            if safe_file_operation(session['csv_file_path'], save_changes):
                flash('Changes saved successfully!', 'success')
                logger.debug("Changes saved to CSV")
        
        # Navigate or download based on action
        if action == 'next' and current_index < len(words) - 1:
            session['current_index'] = current_index + 1
        elif action == 'prev' and current_index > 0:
            session['current_index'] = current_index - 1
        elif action == 'download':
            return redirect(url_for('download_csv'))
        
        return redirect(url_for('index'))
        
    except Exception as e:
        logger.error(f"Error in handle_submit: {e}")
        flash(f"Error saving changes: {str(e)}", 'error')
        return redirect(url_for('index'))


@app.route('/download_csv')
def download_csv():
    try:
        if 'csv_file_path' in session and os.path.exists(session['csv_file_path']):
            def prepare_download():
                # Create a temporary copy for download
                temp_dir = os.path.join(UPLOAD_FOLDER, 'temp')
                os.makedirs(temp_dir, exist_ok=True)
                temp_file = os.path.join(temp_dir, os.path.basename(session['csv_file_path']))
                shutil.copy2(session['csv_file_path'], temp_file)
                return temp_file

            temp_file = safe_file_operation(session['csv_file_path'], prepare_download)
            return send_file(temp_file, as_attachment=True, 
                           download_name=f"updated_{os.path.basename(session['csv_file_path'])}")
        else:
            flash('No CSV file available for download', 'error')
            return redirect(url_for('index'))
    except Exception as e:
        logger.error(f"Error in download_csv: {e}")
        flash(f"Error downloading file: {str(e)}", 'error')
        return redirect(url_for('index'))
       
@app.errorhandler(404)
def not_found_error(error):
    logger.error(f"404 error: {error}")
    return render_template('index.html', data=None), 404

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"500 error: {error}")
    return render_template('index.html', data=None), 500

if __name__ == '__main__':
    app.run()
