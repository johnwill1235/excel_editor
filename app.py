from flask import Flask, render_template, request, send_file, redirect, url_for, flash, session
import pandas as pd
import os
import logging
from werkzeug.utils import secure_filename

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

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def load_dataframe():
    """Load DataFrame from session data and group by word"""
    if 'csv_file_path' in session and os.path.exists(session['csv_file_path']):
        try:
            df = pd.read_csv(session['csv_file_path'])
            # Exclude the grouping column 'word' from the apply operation
            grouped = df.groupby('word', group_keys=False).apply(lambda x: x.to_dict(orient='records')).to_dict()
            return grouped
        except Exception as e:
            logger.error(f"Error loading DataFrame: {e}")
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
                filename = secure_filename(file.filename)
                filepath = os.path.join(UPLOAD_FOLDER, filename)
                file.save(filepath)
                logger.debug(f"File saved to {filepath}")
                
                # Try to read the CSV file
                temp_df = pd.read_csv(filepath)
                logger.debug(f"CSV read successful. Shape: {temp_df.shape}")
                
                # Check for required columns
                missing_columns = [col for col in REQUIRED_COLUMNS if col not in temp_df.columns]
                if missing_columns:
                    logger.warning(f"Missing columns: {missing_columns}")
                    flash(f"Missing required columns: {', '.join(missing_columns)}", 'error')
                    os.remove(filepath)
                    return redirect(url_for('index'))
                
                # Store file path in session
                session['csv_file_path'] = filepath
                session['current_index'] = 0
                
                flash('CSV file loaded successfully!', 'success')
                logger.debug("CSV processing completed successfully")
                
            except Exception as e:
                logger.error(f"Error processing CSV: {e}")
                flash(f"Error processing CSV file: {str(e)}", 'error')
                if os.path.exists(filepath):
                    os.remove(filepath)
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
            flash('Changes saved successfully!', 'success')
            logger.debug("Changes saved to CSV")
        
        # Navigate or download based on action
        if action == 'next' and current_index < len(words) - 1:
            session['current_index'] = current_index + 1
        elif action == 'prev' and current_index > 0:
            session['current_index'] = current_index - 1
        elif action == 'download':
            # Redirect to the download route after saving
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
            return send_file(session['csv_file_path'], as_attachment=True)
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
