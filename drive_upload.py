#!/usr/bin/env python
"""
Upload files or folders to Google Drive with duplicate detection.

The script uses OAuth installed-app credentials. On the first run, place a
Google Cloud OAuth client JSON file at ./credentials.json or pass
--credentials PATH. A reusable token is stored locally in ./token.json.
"""

from __future__ import annotations

import argparse
import hashlib
import mimetypes
import sys
import warnings
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Callable, Iterable

warnings.filterwarnings(
    "ignore",
    message="You are using a Python version .* which Google will stop supporting.*",
    category=FutureWarning,
)

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
from tqdm import tqdm


SCOPES = ["https://www.googleapis.com/auth/drive"]
FOLDER_MIME = "application/vnd.google-apps.folder"


@dataclass(frozen=True)
class LocalFile:
    path: Path
    relative_path: PurePosixPath
    size: int
    md5: str
    sha256: str


@dataclass(frozen=True)
class UploadSummary:
    uploaded: int
    skipped: int
    name_conflicts: int
    total: int


LogCallback = Callable[[str], None]
ProgressCallback = Callable[[LocalFile, int, int], None]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Upload a file or folder to Google Drive and skip exact duplicates."
    )
    parser.add_argument("source", type=Path, help="Local file or folder to upload.")
    parser.add_argument(
        "--drive-folder-id",
        default="root",
        help="Destination Google Drive folder ID. Defaults to root.",
    )
    parser.add_argument(
        "--destination-name",
        help="Optional name for the uploaded file or top-level folder.",
    )
    parser.add_argument(
        "--credentials",
        type=Path,
        default=Path(__file__).with_name("credentials.json"),
        help="OAuth client JSON path. Defaults to ./credentials.json.",
    )
    parser.add_argument(
        "--token",
        type=Path,
        default=Path(__file__).with_name("token.json"),
        help="OAuth token path. Defaults to ./token.json.",
    )
    parser.add_argument(
        "--on-conflict",
        choices=("rename", "skip", "upload"),
        default="rename",
        help=(
            "What to do when a same-name file exists but content differs. "
            "Default: rename."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would happen without uploading or creating folders.",
    )
    return parser.parse_args()


def escape_query_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def drive_query(service, query: str, fields: str):
    results = []
    page_token = None
    while True:
        response = (
            service.files()
            .list(
                q=query,
                spaces="drive",
                fields=f"nextPageToken, files({fields})",
                pageToken=page_token,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            )
            .execute()
        )
        results.extend(response.get("files", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            return results


def authenticate(credentials_path: Path, token_path: Path):
    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
        if not creds.has_scopes(SCOPES):
            creds = None

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())

    if not creds or not creds.valid:
        if not credentials_path.exists():
            raise FileNotFoundError(
                f"OAuth credentials file not found: {credentials_path}\n"
                "Create an OAuth Desktop app in Google Cloud Console, download "
                "the JSON, and save it as credentials.json next to this script."
            )
        flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), SCOPES)
        creds = flow.run_local_server(port=0)
        token_path.write_text(creds.to_json(), encoding="utf-8")

    return build("drive", "v3", credentials=creds, cache_discovery=False)


def file_hashes(path: Path) -> tuple[str, str]:
    md5 = hashlib.md5()
    sha256 = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            md5.update(chunk)
            sha256.update(chunk)
    return md5.hexdigest(), sha256.hexdigest()


def collect_files(source: Path, destination_name: str | None) -> list[LocalFile]:
    source = source.resolve()
    if not source.exists():
        raise FileNotFoundError(f"Source does not exist: {source}")

    files: list[Path]
    if source.is_file():
        files = [source]
        base_parent = source.parent
        top_name = destination_name or source.name
    else:
        files = [p for p in source.rglob("*") if p.is_file()]
        base_parent = source.parent
        top_name = destination_name or source.name

    collected = []
    for path in files:
        if source.is_file():
            relative_path = PurePosixPath(top_name)
        else:
            rel = path.relative_to(base_parent).as_posix()
            source_name = source.name
            if destination_name:
                rel = str(PurePosixPath(destination_name) / PurePosixPath(rel).relative_to(source_name))
            relative_path = PurePosixPath(rel)
        md5, sha256 = file_hashes(path)
        collected.append(
            LocalFile(
                path=path,
                relative_path=relative_path,
                size=path.stat().st_size,
                md5=md5,
                sha256=sha256,
            )
        )
    return collected


def find_child_folder(service, parent_id: str, name: str):
    query = (
        f"'{escape_query_value(parent_id)}' in parents and "
        f"name = '{escape_query_value(name)}' and "
        f"mimeType = '{FOLDER_MIME}' and trashed = false"
    )
    matches = drive_query(service, query, "id, name, modifiedTime")
    return matches[0] if matches else None


def ensure_folder(service, parent_id: str, name: str, dry_run: bool) -> str:
    existing = find_child_folder(service, parent_id, name)
    if existing:
        return existing["id"]

    if dry_run:
        return f"dry-run-folder:{parent_id}/{name}"

    metadata = {"name": name, "mimeType": FOLDER_MIME, "parents": [parent_id]}
    created = (
        service.files()
        .create(body=metadata, fields="id", supportsAllDrives=True)
        .execute()
    )
    return created["id"]


def ensure_parent_path(service, root_folder_id: str, relative_path: PurePosixPath, dry_run: bool) -> str:
    parent_id = root_folder_id
    for part in relative_path.parts[:-1]:
        parent_id = ensure_folder(service, parent_id, part, dry_run)
    return parent_id


def find_same_name_files(service, parent_id: str, name: str):
    query = (
        f"'{escape_query_value(parent_id)}' in parents and "
        f"name = '{escape_query_value(name)}' and "
        "mimeType != 'application/vnd.google-apps.folder' and trashed = false"
    )
    return drive_query(
        service,
        query,
        "id, name, size, md5Checksum, appProperties, webViewLink, modifiedTime",
    )


def classify_duplicate(existing_files: Iterable[dict], local_file: LocalFile) -> tuple[str, dict | None]:
    existing_files = list(existing_files)
    for existing in existing_files:
        app_props = existing.get("appProperties") or {}
        same_size = str(local_file.size) == str(existing.get("size", ""))
        same_md5 = local_file.md5 == existing.get("md5Checksum")
        same_sha256 = local_file.sha256 == app_props.get("localSha256")
        if same_size and (same_md5 or same_sha256):
            return "exact", existing
    if existing_files:
        return "name-conflict", None
    return "new", None


def conflict_name(original_name: str, sha256: str) -> str:
    path = PurePosixPath(original_name)
    suffix = f" ({sha256[:8]})"
    if path.suffix:
        return f"{path.stem}{suffix}{path.suffix}"
    return f"{path.name}{suffix}"


def upload_file(
    service,
    local_file: LocalFile,
    parent_id: str,
    drive_name: str,
    dry_run: bool,
    progress_callback: ProgressCallback | None = None,
    show_progress_bar: bool = True,
):
    mime_type, _ = mimetypes.guess_type(local_file.path.name)
    mime_type = mime_type or "application/octet-stream"

    if dry_run:
        return {"id": "dry-run", "name": drive_name, "webViewLink": ""}

    metadata = {
        "name": drive_name,
        "parents": [parent_id],
        "appProperties": {
            "localSha256": local_file.sha256,
            "localRelativePath": str(local_file.relative_path),
        },
    }
    media = MediaFileUpload(str(local_file.path), mimetype=mime_type, resumable=True)
    request = service.files().create(
        body=metadata,
        media_body=media,
        fields="id, name, webViewLink",
        supportsAllDrives=True,
    )

    response = None
    progress_bar = None
    if show_progress_bar:
        progress_bar = tqdm(
            total=local_file.size,
            unit="B",
            unit_scale=True,
            desc=drive_name,
            leave=False,
        )
    last_progress = 0
    while response is None:
        status, response = request.next_chunk()
        if status:
            current = int(status.resumable_progress)
            if progress_bar:
                progress_bar.update(max(0, current - last_progress))
            if progress_callback:
                progress_callback(local_file, current, local_file.size)
            last_progress = current
    if progress_bar:
        progress_bar.update(max(0, local_file.size - last_progress))
        progress_bar.close()
    if progress_callback:
        progress_callback(local_file, local_file.size, local_file.size)
    return response


def run_upload(
    source: Path,
    drive_folder_id: str = "root",
    destination_name: str | None = None,
    credentials: Path | None = None,
    token: Path | None = None,
    on_conflict: str = "rename",
    dry_run: bool = False,
    log: LogCallback | None = None,
    progress: ProgressCallback | None = None,
    show_progress_bar: bool = True,
) -> UploadSummary:
    credentials = credentials or Path(__file__).with_name("credentials.json")
    token = token or Path(__file__).with_name("token.json")
    log = log or print

    service = authenticate(credentials, token)
    files = collect_files(source, destination_name)
    if not files:
        log("No files found to upload.")
        return UploadSummary(uploaded=0, skipped=0, name_conflicts=0, total=0)

    uploaded = skipped = conflicts = 0

    for local_file in files:
        parent_id = ensure_parent_path(
            service, drive_folder_id, local_file.relative_path, dry_run
        )
        drive_name = local_file.relative_path.name
        existing = find_same_name_files(service, parent_id, drive_name)
        classification, match = classify_duplicate(existing, local_file)

        if classification == "exact":
            skipped += 1
            link = match.get("webViewLink", "") if match else ""
            log(f"SKIP duplicate: {local_file.relative_path} {link}".rstrip())
            continue

        if classification == "name-conflict":
            conflicts += 1
            if on_conflict == "skip":
                skipped += 1
                log(f"SKIP name conflict: {local_file.relative_path}")
                continue
            if on_conflict == "rename":
                drive_name = conflict_name(drive_name, local_file.sha256)
                log(f"RENAME conflict: {local_file.relative_path} -> {drive_name}")
            else:
                log(f"UPLOAD conflict copy: {local_file.relative_path}")

        result = upload_file(
            service,
            local_file,
            parent_id,
            drive_name,
            dry_run,
            progress_callback=progress,
            show_progress_bar=show_progress_bar,
        )
        uploaded += 1
        link = result.get("webViewLink", "")
        action = "WOULD UPLOAD" if dry_run else "UPLOADED"
        log(f"{action}: {local_file.relative_path} {link}".rstrip())

    summary = UploadSummary(
        uploaded=uploaded,
        skipped=skipped,
        name_conflicts=conflicts,
        total=len(files),
    )
    log(
        f"Done. uploaded={summary.uploaded}, skipped={summary.skipped}, "
        f"name_conflicts={summary.name_conflicts}, total={summary.total}"
    )
    return summary


def main() -> int:
    args = parse_args()

    try:
        run_upload(
            source=args.source,
            drive_folder_id=args.drive_folder_id,
            destination_name=args.destination_name,
            credentials=args.credentials,
            token=args.token,
            on_conflict=args.on_conflict,
            dry_run=args.dry_run,
        )
        return 0
    except (FileNotFoundError, HttpError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
