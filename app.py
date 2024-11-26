from flask import Flask, render_template, request, send_file, redirect, url_for, flash
import pandas as pd
import os
import logging
from werkzeug.utils import secure_filename
from datetime import datetime

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'  # Required for flash messages

# Configuration
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'csv'}
REQUIRED_COLUMNS = ["word", "number", "old_definition", "translation",
                    "definition", "example_sentences", "part_of_speech", "collocations"]

# Create uploads directory if it doesn't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def load_dataframe(csv_file_path):
    """Load DataFrame from CSV file and group by word, maintaining number order"""
    if os.path.exists(csv_file_path):
        try:
            df = pd.read_csv(csv_file_path)

            # Replace NaN with empty strings for specific columns
            for col in ['collocations', 'example_sentences']:
                if col in df.columns:
                    df[col] = df[col].fillna('').astype(str)

            # First sort by number to ensure overall numerical order
            df = df.sort_values(by='number', ascending=True)

            # Group by word while maintaining the number order within groups
            grouped = df.groupby('word', group_keys=False).apply(
                lambda x: x.to_dict(orient='records')).to_dict()

            # Sort the grouped dictionary by the minimum number in each word group
            sorted_grouped = dict(sorted(
                grouped.items(),
                key=lambda item: min(entry['number'] for entry in item[1])
            ))

            return sorted_grouped
        except Exception as e:
            logger.error(f"Error loading DataFrame: {e}")
    return None


@app.route('/', methods=['GET'])
def index():
    try:
        csv_file_path = request.args.get('csv_file_path')
        current_index = int(request.args.get('current_index', 0))

        if not csv_file_path or not os.path.exists(csv_file_path):
            return render_template("index.html", entries=None)

        grouped_data = load_dataframe(csv_file_path)

        if grouped_data:
            words = list(grouped_data.keys())
            if not words:
                logger.debug("Grouped data is empty")
                return render_template("index.html", entries=None)

            if current_index >= len(words):
                current_index = len(words) - 1
            if current_index < 0:
                current_index = 0

            current_word = words[current_index]
            entries = grouped_data[current_word]

            logger.debug(f"Data for word '{current_word}' loaded. Number of entries: {len(entries)}")

            return render_template(
                "index.html",
                entries=entries,
                total_words=len(words),
                current_word_index=current_index + 1,
                csv_file_path=csv_file_path,
                current_index=current_index
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
                # Generate unique filename using timestamp
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f"{timestamp}_{secure_filename(file.filename)}"
                filepath = os.path.join(UPLOAD_FOLDER, filename)

                # Save new file
                file.save(filepath)
                logger.debug(f"File saved to {filepath}")

                # Verify CSV columns
                temp_df = pd.read_csv(filepath)
                missing_columns = [col for col in REQUIRED_COLUMNS if col not in temp_df.columns]
                if missing_columns:
                    os.remove(filepath)
                    raise ValueError(f"Missing required columns: {', '.join(missing_columns)}")

                flash('CSV file loaded successfully!', 'success')
                logger.debug("CSV processing completed successfully")

                return redirect(url_for('index', csv_file_path=filepath))

            except Exception as e:
                logger.error(f"Error processing CSV: {e}")
                if os.path.exists(filepath):
                    os.remove(filepath)
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
        action = request.form.get('action')
        csv_file_path = request.form.get('csv_file_path')
        current_index = int(request.form.get('current_index', 0))

        grouped_data = load_dataframe(csv_file_path)
        if grouped_data is None:
            flash('No CSV file loaded', 'error')
            return redirect(url_for('index'))

        words = list(grouped_data.keys())
        current_word = words[current_index]
        entries = grouped_data[current_word]

        # Save current entries
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
        updated_df.to_csv(csv_file_path, index=False)

        flash('Changes saved successfully!', 'success')
        logger.debug("Changes saved to CSV")

        # Navigate or download based on action
        if action == 'next':
            if current_index < len(words) - 1:
                current_index += 1
        elif action == 'prev':
            if current_index > 0:
                current_index -= 1
        elif action == 'download':
            return redirect(url_for('download_csv', csv_file_path=csv_file_path))
        elif action == 'jump':
            jump_to_index = request.form.get('jump_to_index')
            try:
                jump_to_index = int(jump_to_index) - 1  # Adjust for 1-based index
                if 0 <= jump_to_index < len(words):
                    current_index = jump_to_index
                else:
                    flash(f"Invalid index: {jump_to_index + 1}. Must be between 1 and {len(words)}.", 'error')
            except ValueError:
                flash(f"Invalid input: {jump_to_index}. Please enter a valid number.", 'error')

        return redirect(url_for('index', csv_file_path=csv_file_path, current_index=current_index))

    except Exception as e:
        logger.error(f"Error in handle_submit: {e}")
        flash(f"Error saving changes: {str(e)}", 'error')
        return redirect(url_for('index'))


@app.route('/download_csv')
def download_csv():
    try:
        csv_file_path = request.args.get('csv_file_path')
        if csv_file_path and os.path.exists(csv_file_path):
            # Read the original CSV file
            df = pd.read_csv(csv_file_path)

            # Sort the DataFrame by 'number' column in ascending order
            sorted_df = df.sort_values(by='number', ascending=True)

            # Create a temporary copy for download
            temp_dir = os.path.join(UPLOAD_FOLDER, 'temp')
            os.makedirs(temp_dir, exist_ok=True)
            temp_file = os.path.join(temp_dir, os.path.basename(csv_file_path))

            # Save the sorted DataFrame to the temporary file
            sorted_df.to_csv(temp_file, index=False)

            return send_file(
                temp_file,
                as_attachment=True,
                download_name=f"sorted_{os.path.basename(csv_file_path)}"
            )
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
    return render_template('index.html', entries=None), 404


@app.errorhandler(500)
def internal_error(error):
    logger.error(f"500 error: {error}")
    return render_template('index.html', entries=None), 500


if __name__ == '__main__':
    app.run(debug=True)
