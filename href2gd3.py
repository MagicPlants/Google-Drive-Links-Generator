import os
import pandas as pd
import requests
import threading
from tkinter import *
from tkinter import filedialog, messagebox
from tkinter.ttk import Progressbar
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload


class LinkConverterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Images to Google Drive Links Converter")
        self.root.geometry("800x800")

        self.file_path = None
        self.csv_data = None
        self.json_path = None
        self.credentials = None
        self.drive_service = None
        self.folder_id = None
        self.uploaded_files = {}  # Tracks {filename: google_drive_link}

        # File selection frame
        file_frame = Frame(root, padx=10, pady=10)
        file_frame.pack(fill="x")
        self.file_label = Label(file_frame, text="No CSV file selected", anchor="w")
        self.file_label.pack(side=LEFT, expand=True, fill="x")
        self.browse_button = Button(file_frame, text="Browse CSV", command=self.browse_file)
        self.browse_button.pack(side=RIGHT)

        # JSON file selection frame
        json_frame = Frame(root, padx=10, pady=10)
        json_frame.pack(fill="x")
        self.json_label = Label(json_frame, text="No JSON credentials file selected", anchor="w")
        self.json_label.pack(side=LEFT, expand=True, fill="x")
        self.json_button = Button(json_frame, text="Browse JSON File", command=self.browse_json)
        self.json_button.pack(side=RIGHT)

        # Folder ID and Selection
        folder_frame = Frame(root, padx=10, pady=10)
        folder_frame.pack(fill="x")
        self.folder_label = Label(folder_frame, text="Google Drive Folder ID:", anchor="w")
        self.folder_label.pack(side=LEFT)
        self.folder_entry = Entry(folder_frame)
        self.folder_entry.pack(side=LEFT, expand=True, fill="x")
        self.list_folders_button = Button(folder_frame, text="List Folders", command=self.list_folders)
        self.list_folders_button.pack(side=RIGHT)

        # Folder Listbox
        folder_list_frame = Frame(root, padx=10, pady=10)
        folder_list_frame.pack(fill="x")
        self.folder_list_label = Label(folder_list_frame, text="Available Folders:")
        self.folder_list_label.pack(anchor="w")
        self.folder_listbox = Listbox(folder_list_frame, height=10, width=80)
        self.folder_listbox.pack(side=LEFT, fill="both", expand=True)
        self.select_folder_button = Button(folder_list_frame, text="Select Folder", command=self.select_folder)
        self.select_folder_button.pack(side=RIGHT)

        # Progress bar
        self.progress_label = Label(root, text="Progress: 0%")
        self.progress_label.pack()
        self.progress = Progressbar(root, orient=HORIZONTAL, length=600, mode="determinate")
        self.progress.pack(pady=10)

        # Lists for links
        list_frame = Frame(root)
        list_frame.pack(pady=10)
        self.pending_label = Label(list_frame, text="Links to Convert")
        self.pending_label.grid(row=0, column=0)
        self.done_label = Label(list_frame, text="Links Done")
        self.done_label.grid(row=0, column=1)
        self.pending_list = Listbox(list_frame, height=10, width=50)
        self.pending_list.grid(row=1, column=0, padx=5)
        self.done_list = Listbox(list_frame, height=10, width=50)
        self.done_list.grid(row=1, column=1, padx=5)

        # Debug log
        self.debug_label = Label(root, text="Debug Log")
        self.debug_label.pack()
        self.debug_text = Text(root, height=10, width=100)
        self.debug_text.pack(pady=5)

        # Buttons frame
        button_frame = Frame(root)
        button_frame.pack(pady=10)
        self.convert_button = Button(button_frame, text="Start Conversion", command=self.start_processing)
        self.convert_button.grid(row=0, column=0, padx=5)
        self.clear_button = Button(button_frame, text="Clear Lists", command=self.clear_lists)
        self.clear_button.grid(row=0, column=1, padx=5)

    def browse_file(self):
        self.file_path = filedialog.askopenfilename(filetypes=[("CSV files", "*.csv")])
        if self.file_path:
            self.file_label.config(text=self.file_path)
            self.load_csv()

    def browse_json(self):
        self.json_path = filedialog.askopenfilename(filetypes=[("JSON files", "*.json")])
        if self.json_path:
            self.json_label.config(text=self.json_path)
            self.debug_log(f"Selected JSON credentials file: {self.json_path}")

    def authenticate_drive(self):
        if not self.json_path:
            messagebox.showerror("Error", "Please select a JSON credentials file.")
            return None

        try:
            # Authenticate with Google Drive
            self.debug_log("Authenticating with Google Drive...")
            self.credentials = Credentials.from_service_account_file(
                self.json_path,
                scopes=['https://www.googleapis.com/auth/drive.file']
            )
            self.drive_service = build('drive', 'v3', credentials=self.credentials)
            self.debug_log("Authentication successful!", "green")
            return self.drive_service
        except Exception as e:
            self.debug_log(f"Authentication failed: {str(e)}", "red")
            return None

    def list_folders(self):
        drive_service = self.authenticate_drive()
        if not drive_service:
            return

        try:
            self.debug_log("Fetching list of folders...")
            results = drive_service.files().list(
                q="mimeType='application/vnd.google-apps.folder'",
                spaces='drive',
                fields='nextPageToken, files(id, name)',
                pageSize=50
            ).execute()
            folders = results.get('files', [])
            self.folder_listbox.delete(0, END)
            for folder in folders:
                self.folder_listbox.insert(END, f"{folder['name']} (ID: {folder['id']})")
            self.debug_log(f"Found {len(folders)} folders.")
        except Exception as e:
            self.debug_log(f"Failed to fetch folders: {str(e)}", "red")

    def select_folder(self):
        selected = self.folder_listbox.get(ACTIVE)
        if selected:
            folder_id = selected.split("(ID: ")[1][:-1]  # Extract the ID from the selection
            self.folder_entry.delete(0, END)
            self.folder_entry.insert(0, folder_id)
            self.debug_log(f"Selected Folder ID: {folder_id}")

    def load_csv(self):
        try:
            self.csv_data = pd.read_csv(self.file_path)
            if "Links" in self.csv_data.columns:
                self.pending_list.delete(0, END)
                for link in self.csv_data["Links"]:
                    self.pending_list.insert(END, link)
                self.debug_log("CSV loaded successfully!")
            else:
                messagebox.showerror("Error", "CSV must contain a 'Links' column.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load CSV: {str(e)}")
            self.debug_log(f"Error loading CSV: {str(e)}")

    def debug_log(self, message, color="black"):
        self.debug_text.insert(END, message + "\n")
        self.debug_text.tag_add("start", "end-2l", "end-1l")
        self.debug_text.tag_config("start", foreground=color)
        self.debug_text.see(END)

    def start_processing(self):
        threading.Thread(target=self.process_links).start()

    def clear_lists(self):
        self.pending_list.delete(0, END)
        self.done_list.delete(0, END)
        self.debug_text.delete(1.0, END)
        self.debug_log("Cleared all lists and logs.")

# Run the application
if __name__ == "__main__":
    root = Tk()
    app = LinkConverterApp(root)
    root.mainloop()
