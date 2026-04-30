# Google Drive Uploader

Uploads a file or folder to Google Drive with rclone and duplicate-aware copy options.

## Setup

Install rclone first:

```powershell
install_rclone.bat
```

The installer uses `winget install --id Rclone.Rclone --exact --source winget`. If `winget` is not available, it opens the official rclone download page: https://rclone.org/downloads/.

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

圖形介面可以選擇本機檔案或資料夾、輸入 rclone remote 名稱與 Google Drive 目標路徑、選擇同名檔案處理方式，並支援「只預覽，不實際上傳」。

GUI 不再需要 `credentials.json`。按「建立/授權」後會執行 rclone 的 Google Drive remote 設定，rclone 會自動開瀏覽器進行 OAuth，token 會存到 rclone 自己的設定檔。

## rclone command line usage

Upload one file to your Drive root:

```powershell
rclone copy "C:\Users\steven\Downloads\example.zip" gdrive: --checksum
```

Upload a folder:

```powershell
rclone copy "C:\Users\steven\Downloads\Documents" gdrive:Documents --checksum --create-empty-src-dirs
```

Preview without uploading:

```powershell
rclone copy "C:\path\to\folder" gdrive:Backup --checksum --dry-run
```

## Duplicate behavior

- `用 checksum 判斷，相同略過，不同更新`：uses `rclone copy --checksum`.
- `只要同名已存在就略過`：uses `rclone copy --ignore-existing`.
- `不檢查，全部重新上傳`：uses `rclone copy --ignore-times`.

## Legacy Google API script

The older Google API script is still present as `drive_upload.py`, but the GUI now uses rclone.

Install its Python dependencies only if you still want to use that legacy script:

```powershell
python -m pip install -r requirements.txt
```
