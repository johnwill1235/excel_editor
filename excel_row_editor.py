import sys
import pandas as pd
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QTextEdit, QPushButton, QVBoxLayout, 
    QHBoxLayout, QFileDialog, QProgressBar
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont

class CSVEditorApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CSV Row Editor")
        self.showFullScreen()  # Open in full-screen mode

        # Predefined columns
        self.columns = [
            "word", "number", "translation", "definition", 
            "example_sentences", "part_of_speech", "collocations"
        ]

        # Initialize variables
        self.df = None
        self.total_rows = 0
        self.current_index = 0
        self.inputs = {}

        # Initialize UI
        self.init_ui()

    def init_ui(self):
        # Main layout
        self.layout = QVBoxLayout()

        # Load CSV Button
        self.load_button = QPushButton("Load CSV File")
        self.load_button.clicked.connect(self.load_csv)
        self.load_button.setFont(QFont("Arial", 18))
        self.layout.addWidget(self.load_button)

        # Container for input fields
        self.input_container = QVBoxLayout()
        self.layout.addLayout(self.input_container)

        # Navigation Buttons
        nav_layout = QHBoxLayout()
        self.prev_button = QPushButton("Previous")
        self.prev_button.setFont(QFont("Arial", 18))
        self.prev_button.clicked.connect(self.prev_row)
        self.prev_button.setEnabled(False)

        self.save_row_button = QPushButton("Save Row")
        self.save_row_button.setFont(QFont("Arial", 18))
        self.save_row_button.clicked.connect(self.save_changes)
        self.save_row_button.setEnabled(False)

        self.next_button = QPushButton("Save & Next")
        self.next_button.setFont(QFont("Arial", 18))
        self.next_button.clicked.connect(self.next_row)
        self.next_button.setEnabled(False)

        self.exit_button = QPushButton("Save & Exit")
        self.exit_button.setFont(QFont("Arial", 18))
        self.exit_button.clicked.connect(self.exit_app)

        # Add buttons to layout with increased spacing
        nav_layout.addWidget(self.prev_button)
        nav_layout.addWidget(self.save_row_button)
        nav_layout.addWidget(self.next_button)
        nav_layout.addWidget(self.exit_button)
        self.layout.addLayout(nav_layout)

        # Progress Bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.layout.addWidget(self.progress_bar)

        # Status Label
        self.status_label = QLabel("Please load a CSV file to begin.")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setFont(QFont("Arial", 20))
        self.layout.addWidget(self.status_label)

        self.setLayout(self.layout)

    def load_csv(self):
        options = QFileDialog.Options()
        options |= QFileDialog.ReadOnly
        file_path, _ = QFileDialog.getOpenFileName(
            self, 
            "Select CSV File", 
            "", 
            "CSV Files (*.csv)", 
            options=options
        )
        if file_path:
            try:
                self.df = pd.read_csv(file_path, usecols=self.columns)  # Load only the required columns
                self.total_rows = len(self.df)
                self.current_index = 0

                # Clear previous input fields if any
                self.clear_inputs()

                # Create input fields for the required columns
                for column in self.columns:
                    h_layout = QHBoxLayout()
                    label = QLabel(column)
                    label.setFixedWidth(150)
                    label.setFont(QFont("Arial", 20))

                    line_edit = QTextEdit()
                    line_edit.setFont(QFont("Arial", 20))

                    # Fixed heights based on column type
                    if column in ["word", "number", "part_of_speech"]:
                        line_edit.setFixedHeight(40)  # Fixed height to match Arial 20 text size

                        if column in ["word", "number"]:
                            line_edit.setReadOnly(True)
                            line_edit.setStyleSheet("background-color: lightgrey;")  # Grey out for read-only fields
                    elif column == "example_sentences":
                        line_edit.setFixedHeight(250)  # Larger height for example_sentences
                    elif column == "definition" or column == "translation" or column == "collocations":
                        line_edit.setFixedHeight(40)

                    self.inputs[column] = line_edit
                    h_layout.addWidget(label)
                    h_layout.addWidget(line_edit)
                    self.input_container.addLayout(h_layout)

                # Enable navigation buttons
                self.prev_button.setEnabled(False)
                self.next_button.setEnabled(True)
                self.save_row_button.setEnabled(True)

                # Initialize progress bar
                self.progress_bar.setMaximum(self.total_rows)
                self.progress_bar.setValue(0)
                self.progress_bar.setVisible(True)

                # Load the first row
                self.load_row()
                self.status_label.setText(f"Loaded '{file_path}' with {self.total_rows} rows.")
                self.csv_file_path = file_path

            except Exception as e:
                self.status_label.setText(f"Error loading CSV: {e}")

    def clear_inputs(self):
        while self.input_container.count():
            child = self.input_container.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        self.inputs.clear()

    def load_row(self):
        if self.df is not None and 0 <= self.current_index < self.total_rows:
            row = self.df.iloc[self.current_index]
            for column in self.columns:
                self.inputs[column].setPlainText(str(row[column]))
            self.update_progress()

    def update_progress(self):
        self.status_label.setText(f"Editing Row {self.current_index + 1} of {self.total_rows}")
        self.progress_bar.setValue(self.current_index + 1)
        percent_done = int(((self.current_index + 1) / self.total_rows) * 100)
        self.progress_bar.setFormat(f"{self.current_index + 1}/{self.total_rows} ({percent_done}%)")

    def save_changes(self):
        if self.df is not None and 0 <= self.current_index < self.total_rows:
            for column in self.columns:
                self.df.at[self.current_index, column] = self.inputs[column].toPlainText()

            # Save to CSV immediately after saving row
            try:
                self.df.to_csv(self.csv_file_path, index=False)
                self.status_label.setText(f"Changes saved for row {self.current_index + 1}. File updated.")
            except Exception as e:
                self.status_label.setText(f"Error saving CSV: {e}")

    def next_row(self):
        self.save_changes()
        if self.current_index < self.total_rows - 1:
            self.current_index += 1
            self.load_row()
            self.status_label.setText("Moved to the next row.")
        else:
            self.status_label.setText("You have reached the last row.")
            self.next_button.setEnabled(False)

    def prev_row(self):
        self.save_changes()
        if self.current_index > 0:
            self.current_index -= 1
            self.load_row()
            self.status_label.setText("Moved to the previous row.")
        else:
            self.status_label.setText("You are at the first row.")
            self.prev_button.setEnabled(False)

    def exit_app(self):
        self.save_changes()
        self.close()

def main():
    app = QApplication(sys.argv)
    editor = CSVEditorApp()
    editor.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
