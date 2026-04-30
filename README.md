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

## 繁體中文圖形介面

在 Windows 可直接雙擊：

```powershell
start_gui.bat
```

或使用命令啟動：

Launch the Traditional Chinese GUI:

```powershell
python .\drive_upload_gui.py
```

圖形介面可以選擇本機檔案或資料夾、輸入 Google Drive 目標資料夾 ID、選擇同名檔案處理方式，並支援「只預覽，不實際上傳」。

GUI 啟動時會自動檢查 OAuth 授權：

- 如果已經有 `token.json`，會直接沿用。
- 如果沒有 `token.json` 但找到 `credentials.json`，會自動開啟瀏覽器進行 Google OAuth 授權，完成後自動存成 `token.json`。
- 如果找不到 `credentials.json`，GUI 會提示你選擇 Google OAuth Desktop app JSON 檔，選好後會立即啟動授權。
- GUI 會把 credentials/token 路徑存在本機 `gui_settings.json`，此檔案已被 `.gitignore` 排除。

## Command line usage

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
