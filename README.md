# Google Drive Uploader

Uploads a file or folder to Google Drive and detects duplicates before upload.

## Setup

1. Create a Google Cloud OAuth client:
   - Google Cloud Console -> APIs & Services -> Library -> enable **Google Drive API**
   - APIs & Services -> Credentials -> Create Credentials -> OAuth client ID
   - Application type: **Desktop app**
   - Download the JSON file
   - The first authorization asks for Google Drive access so the script can search the destination folder and detect existing duplicates.
2. Save the JSON as:

```powershell
C:\Users\steven\Downloads\google-drive-uploader\credentials.json
```

3. Install dependencies:

```powershell
cd C:\Users\steven\Downloads\google-drive-uploader
python -m pip install -r requirements.txt
```

## Usage

Upload one file to your Drive root:

```powershell
python .\drive_upload.py "C:\Users\steven\Downloads\example.zip"
```

Upload a folder to your Drive root:

```powershell
python .\drive_upload.py "C:\Users\steven\Downloads\Documents"
```

Upload into a specific Google Drive folder:

```powershell
python .\drive_upload.py "C:\path\to\folder" --drive-folder-id "YOUR_FOLDER_ID"
```

Preview without uploading:

```powershell
python .\drive_upload.py "C:\path\to\folder" --dry-run
```

## Duplicate behavior

- Exact duplicate in the same Drive folder: skipped.
- Same name but different content: renamed by default, for example `report (a1b2c3d4).pdf`.
- Change same-name behavior with:

```powershell
python .\drive_upload.py "C:\path\to\folder" --on-conflict skip
python .\drive_upload.py "C:\path\to\folder" --on-conflict upload
python .\drive_upload.py "C:\path\to\folder" --on-conflict rename
```

Exact duplicate detection uses file size plus Google Drive MD5 when available, and also writes a local SHA-256 value into Drive app metadata for files uploaded by this script.
