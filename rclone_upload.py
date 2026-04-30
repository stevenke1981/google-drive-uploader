#!/usr/bin/env python
"""
rclone-backed uploader helpers for Google Drive.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


LogCallback = Callable[[str], None]


@dataclass(frozen=True)
class RcloneSummary:
    returncode: int
    command: list[str]


def find_rclone() -> str | None:
    return shutil.which("rclone")


def normalize_remote(remote_name: str) -> str:
    remote_name = remote_name.strip().rstrip(":")
    if not remote_name:
        raise ValueError("Remote name is required.")
    return remote_name


def remote_target(remote_name: str, remote_path: str) -> str:
    remote_name = normalize_remote(remote_name)
    remote_path = remote_path.strip().replace("\\", "/").strip("/")
    if remote_path:
        return f"{remote_name}:{remote_path}"
    return f"{remote_name}:"


def list_remotes(rclone_path: str = "rclone") -> list[str]:
    result = subprocess.run(
        [rclone_path, "listremotes"],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return [line.strip().rstrip(":") for line in result.stdout.splitlines() if line.strip()]


def remote_exists(remote_name: str, rclone_path: str = "rclone") -> bool:
    return normalize_remote(remote_name) in list_remotes(rclone_path)


def configure_drive_remote(
    remote_name: str,
    rclone_path: str = "rclone",
    log: LogCallback | None = None,
) -> RcloneSummary:
    remote_name = normalize_remote(remote_name)
    log = log or print
    command = [rclone_path, "config", "create", remote_name, "drive", "scope", "drive"]
    log("執行：" + " ".join(command))
    return _run_streaming(command, log)


def open_interactive_config(
    rclone_path: str = "rclone",
    log: LogCallback | None = None,
) -> RcloneSummary:
    log = log or print
    command = [rclone_path, "config"]
    log("執行：" + " ".join(command))
    return _run_streaming(command, log)


def upload_with_rclone(
    source: Path,
    remote_name: str,
    remote_path: str = "",
    conflict_mode: str = "checksum",
    dry_run: bool = False,
    rclone_path: str = "rclone",
    log: LogCallback | None = None,
) -> RcloneSummary:
    source = source.resolve()
    if not source.exists():
        raise FileNotFoundError(f"Source does not exist: {source}")

    log = log or print
    target = remote_target(remote_name, remote_path)
    command = [
        rclone_path,
        "copy",
        str(source),
        target,
        "--progress",
        "--stats-one-line",
        "--create-empty-src-dirs",
    ]

    if conflict_mode == "checksum":
        command.append("--checksum")
    elif conflict_mode == "ignore_existing":
        command.append("--ignore-existing")
    elif conflict_mode == "force":
        command.append("--ignore-times")
    else:
        raise ValueError(f"Unsupported conflict mode: {conflict_mode}")

    if dry_run:
        command.append("--dry-run")

    log("執行：" + " ".join(command))
    return _run_streaming(command, log)


def _run_streaming(command: list[str], log: LogCallback) -> RcloneSummary:
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )

    assert process.stdout is not None
    for line in process.stdout:
        line = line.rstrip()
        if line:
            log(line)
    returncode = process.wait()
    if returncode != 0:
        log(f"rclone 結束代碼：{returncode}")
    return RcloneSummary(returncode=returncode, command=command)
