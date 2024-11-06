from flask import Flask, render_template, request, redirect, url_for
import pandas as pd

app = Flask(__name__)

# Global variables
df = None
current_index = 0
csv_file_path = ""
columns = ["word", "number", "old_definition", "translation", "definition", "example_sentences", "part_of_speech", "collocations"]

@app.route('/', methods=['GET'])
def index():
    global df, current_index
    if df is not None:
        row = df.iloc[current_index]
        data = {column: row[column] for column in columns}
        return render_template("index.html", data=data, total_rows=len(df), current_row=current_index + 1)
    return render_template("index.html", data=None)

@app.route('/load_csv', methods=['POST'])
def load_csv():
    global df, current_index, csv_file_path
    file = request.files.get('csv_file')
    if file and file.filename.endswith('.csv'):
        csv_file_path = file.filename
        file.save(csv_file_path)  # Save the uploaded file
        try:
            df = pd.read_csv(csv_file_path, usecols=columns)
            current_index = 0
        except Exception as e:
            return redirect(url_for('index'))
    return redirect(url_for('index'))

@app.route('/handle_submit', methods=['POST'])
def handle_submit():
    global df, current_index, csv_file_path
    if df is None:
        return redirect(url_for('index'))
    
    action = request.form.get('action')
    
    # Save current row if action is 'save', 'next', or 'prev'
    if action in ['save', 'next', 'prev']:
        for column in columns:
            if column in ['word', 'number']:
                continue  # Skip read-only fields
            df.at[current_index, column] = request.form.get(column, '')
        
        # Save to CSV
        df.to_csv(csv_file_path, index=False)
    
    # Navigate based on action
    if action == 'next' and current_index < len(df) - 1:
        current_index += 1
    elif action == 'prev' and current_index > 0:
        current_index -= 1
    
    return redirect(url_for('index'))

if __name__ == "__main__":
    app.run(debug=True)
