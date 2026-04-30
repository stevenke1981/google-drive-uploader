#!/usr/bin/env python
"""
Traditional Chinese GUI for the Google Drive uploader.
"""

from __future__ import annotations

import json
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from googleapiclient.errors import HttpError

from drive_upload import authenticate, run_upload


APP_DIR = Path(__file__).resolve().parent
DEFAULT_CREDENTIALS = APP_DIR / "credentials.json"
DEFAULT_TOKEN = APP_DIR / "token.json"
SETTINGS_PATH = APP_DIR / "gui_settings.json"

CONFLICT_LABELS = {
    "rename": "同名但內容不同時自動改名",
    "skip": "同名但內容不同時略過",
    "upload": "同名但內容不同時仍上傳",
}
CONFLICT_VALUES = {label: value for value, label in CONFLICT_LABELS.items()}


class DriveUploaderApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Google Drive 上傳工具")
        self.geometry("760x560")
        self.minsize(680, 500)

        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.worker: threading.Thread | None = None
        self.auth_worker: threading.Thread | None = None
        self.settings = self._load_settings()

        self.source_var = tk.StringVar()
        self.drive_folder_var = tk.StringVar(value=self.settings.get("drive_folder_id", "root"))
        self.destination_name_var = tk.StringVar()
        self.credentials_var = tk.StringVar(
            value=self.settings.get("credentials_path", str(DEFAULT_CREDENTIALS))
        )
        self.token_var = tk.StringVar(value=self.settings.get("token_path", str(DEFAULT_TOKEN)))
        self.conflict_var = tk.StringVar(value=CONFLICT_LABELS["rename"])
        self.dry_run_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="尚未開始")
        self.auth_status_var = tk.StringVar(value="授權狀態：尚未檢查")
        self.progress_var = tk.DoubleVar(value=0)

        self._build_ui()
        self.after(120, self._drain_events)
        self.after(450, self._auto_authorize)

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        form = ttk.Frame(self, padding=16)
        form.grid(row=0, column=0, sticky="ew")
        form.columnconfigure(1, weight=1)

        self._path_row(form, 0, "來源檔案或資料夾", self.source_var, self._choose_file, self._choose_folder)
        self._entry_row(form, 1, "Drive 目標資料夾 ID", self.drive_folder_var)
        self._entry_row(form, 2, "上傳後名稱（可留空）", self.destination_name_var)
        self._path_row(form, 3, "OAuth credentials.json", self.credentials_var, self._choose_credentials)
        self._path_row(form, 4, "本機 token.json", self.token_var, self._choose_token_save_path)

        ttk.Label(form, text="授權狀態").grid(row=5, column=0, sticky="w", pady=6)
        auth_row = ttk.Frame(form)
        auth_row.grid(row=5, column=1, sticky="ew", pady=6)
        auth_row.columnconfigure(0, weight=1)
        ttk.Label(auth_row, textvariable=self.auth_status_var).grid(row=0, column=0, sticky="w")
        self.auth_button = ttk.Button(auth_row, text="重新授權", command=self._start_authorization)
        self.auth_button.grid(row=0, column=1, sticky="e")

        ttk.Label(form, text="重複檔案處理").grid(row=6, column=0, sticky="w", pady=6)
        conflict = ttk.Combobox(
            form,
            textvariable=self.conflict_var,
            values=list(CONFLICT_VALUES),
            state="readonly",
        )
        conflict.grid(row=6, column=1, sticky="ew", pady=6)

        ttk.Checkbutton(
            form,
            text="只預覽，不實際上傳",
            variable=self.dry_run_var,
        ).grid(row=7, column=1, sticky="w", pady=6)

        actions = ttk.Frame(form)
        actions.grid(row=8, column=1, sticky="e", pady=(10, 0))
        self.start_button = ttk.Button(actions, text="開始上傳", command=self._start_upload)
        self.start_button.grid(row=0, column=0, padx=(0, 8))
        ttk.Button(actions, text="清除紀錄", command=self._clear_log).grid(row=0, column=1)

        output = ttk.Frame(self, padding=(16, 0, 16, 16))
        output.grid(row=1, column=0, sticky="nsew")
        output.columnconfigure(0, weight=1)
        output.rowconfigure(2, weight=1)

        ttk.Label(output, textvariable=self.status_var).grid(row=0, column=0, sticky="w")
        ttk.Progressbar(
            output,
            variable=self.progress_var,
            maximum=100,
            mode="determinate",
        ).grid(row=1, column=0, sticky="ew", pady=(6, 10))

        self.log_text = tk.Text(output, height=14, wrap="word")
        self.log_text.grid(row=2, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(output, orient="vertical", command=self.log_text.yview)
        scroll.grid(row=2, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=scroll.set)

    def _entry_row(
        self,
        parent: ttk.Frame,
        row: int,
        label: str,
        variable: tk.StringVar,
    ) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=6)
        ttk.Entry(parent, textvariable=variable).grid(row=row, column=1, sticky="ew", pady=6)

    def _path_row(
        self,
        parent: ttk.Frame,
        row: int,
        label: str,
        variable: tk.StringVar,
        *commands,
    ) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=6)
        ttk.Entry(parent, textvariable=variable).grid(row=row, column=1, sticky="ew", pady=6)
        buttons = ttk.Frame(parent)
        buttons.grid(row=row, column=2, sticky="e", padx=(8, 0), pady=6)
        labels = ("選檔", "選資料夾") if len(commands) == 2 else ("瀏覽",)
        for index, command in enumerate(commands):
            ttk.Button(buttons, text=labels[index], command=command).grid(
                row=0,
                column=index,
                padx=(0 if index == 0 else 6, 0),
            )

    def _choose_file(self) -> None:
        path = filedialog.askopenfilename(title="選擇要上傳的檔案")
        if path:
            self.source_var.set(path)

    def _choose_folder(self) -> None:
        path = filedialog.askdirectory(title="選擇要上傳的資料夾")
        if path:
            self.source_var.set(path)

    def _choose_credentials(self) -> None:
        path = filedialog.askopenfilename(
            title="選擇 credentials.json",
            filetypes=(("JSON 檔案", "*.json"), ("所有檔案", "*.*")),
        )
        if path:
            self.credentials_var.set(path)
            self._save_settings()
            self._start_authorization()

    def _choose_token_save_path(self) -> None:
        path = filedialog.asksaveasfilename(
            title="選擇 token.json 儲存位置",
            defaultextension=".json",
            filetypes=(("JSON 檔案", "*.json"), ("所有檔案", "*.*")),
        )
        if path:
            self.token_var.set(path)
            self._save_settings()

    def _load_settings(self) -> dict:
        if not SETTINGS_PATH.exists():
            return {}
        try:
            return json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def _save_settings(self) -> None:
        data = {
            "credentials_path": self.credentials_var.get().strip(),
            "token_path": self.token_var.get().strip(),
            "drive_folder_id": self.drive_folder_var.get().strip() or "root",
        }
        SETTINGS_PATH.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _auto_authorize(self) -> None:
        token = Path(self.token_var.get().strip() or DEFAULT_TOKEN)
        credentials = Path(self.credentials_var.get().strip() or DEFAULT_CREDENTIALS)

        if token.exists():
            self.auth_status_var.set(f"授權狀態：已找到 token ({token.name})")
            self._append_log(f"已找到授權 token：{token}")
            return

        if credentials.exists():
            self._append_log("尚未找到 token，將自動開啟瀏覽器進行 Google OAuth 授權。")
            self._start_authorization()
            return

        self.auth_status_var.set("授權狀態：請選擇 credentials.json")
        self._append_log("找不到 credentials.json，請先選擇 Google OAuth Desktop app JSON 檔。")
        if messagebox.askyesno(
            "需要 OAuth 檔案",
            "找不到 credentials.json。是否現在選擇 Google OAuth Desktop app JSON 檔？",
        ):
            self._choose_credentials()

    def _start_authorization(self) -> None:
        if self.auth_worker and self.auth_worker.is_alive():
            return

        credentials = Path(self.credentials_var.get().strip() or DEFAULT_CREDENTIALS)
        token = Path(self.token_var.get().strip() or DEFAULT_TOKEN)
        if not credentials.exists():
            messagebox.showwarning("缺少 OAuth 檔案", "請先選擇 credentials.json。")
            self.auth_status_var.set("授權狀態：缺少 credentials.json")
            return

        self._save_settings()
        self.auth_button.configure(state="disabled")
        self.status_var.set("正在進行 Google OAuth 授權...")
        self.auth_status_var.set("授權狀態：授權中，請依瀏覽器指示登入")
        self._append_log("正在啟動 OAuth 授權；完成後 token 會自動存檔。")
        self.auth_worker = threading.Thread(
            target=self._authorization_worker,
            args=(credentials, token),
            daemon=True,
        )
        self.auth_worker.start()

    def _authorization_worker(self, credentials: Path, token: Path) -> None:
        try:
            authenticate(credentials, token)
            self.events.put(("auth_done", str(token)))
        except (FileNotFoundError, HttpError, ValueError, OSError) as exc:
            self.events.put(("auth_error", str(exc)))

    def _start_upload(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        if self.auth_worker and self.auth_worker.is_alive():
            messagebox.showinfo("授權中", "Google OAuth 授權尚未完成，請先完成瀏覽器登入。")
            return

        source = self.source_var.get().strip()
        if not source:
            messagebox.showwarning("缺少來源", "請先選擇要上傳的檔案或資料夾。")
            return

        credentials = self.credentials_var.get().strip()
        if not credentials:
            messagebox.showwarning("缺少 OAuth 檔案", "請選擇 credentials.json。")
            return

        self._save_settings()
        self.start_button.configure(state="disabled")
        self.progress_var.set(0)
        self.status_var.set("準備上傳...")
        self._append_log("開始處理")

        options = {
            "source": Path(source),
            "drive_folder_id": self.drive_folder_var.get().strip() or "root",
            "destination_name": self.destination_name_var.get().strip() or None,
            "credentials": Path(credentials),
            "token": Path(self.token_var.get().strip() or DEFAULT_TOKEN),
            "on_conflict": CONFLICT_VALUES[self.conflict_var.get()],
            "dry_run": self.dry_run_var.get(),
        }

        self.worker = threading.Thread(target=self._upload_worker, args=(options,), daemon=True)
        self.worker.start()

    def _upload_worker(self, options: dict) -> None:
        try:
            summary = run_upload(
                **options,
                log=lambda message: self.events.put(("log", message)),
                progress=lambda local_file, current, total: self.events.put(
                    ("progress", (str(local_file.relative_path), current, total))
                ),
                show_progress_bar=False,
            )
            self.events.put(("done", summary))
        except (FileNotFoundError, HttpError, ValueError, OSError) as exc:
            self.events.put(("error", str(exc)))

    def _drain_events(self) -> None:
        while True:
            try:
                event, payload = self.events.get_nowait()
            except queue.Empty:
                break

            if event == "log":
                self._append_log(str(payload))
            elif event == "progress":
                relative_path, current, total = payload
                percent = 100 if total == 0 else min(100, current / total * 100)
                self.progress_var.set(percent)
                self.status_var.set(f"上傳中：{relative_path} ({percent:.0f}%)")
            elif event == "done":
                summary = payload
                self.progress_var.set(100)
                self.status_var.set(
                    f"完成：上傳 {summary.uploaded}，略過 {summary.skipped}，同名衝突 {summary.name_conflicts}"
                )
                self.start_button.configure(state="normal")
                messagebox.showinfo("完成", "上傳流程已完成。")
            elif event == "auth_done":
                self.auth_button.configure(state="normal")
                self.status_var.set("OAuth 授權完成")
                self.auth_status_var.set("授權狀態：完成，token 已存檔")
                self._append_log(f"OAuth 授權完成，token 已存檔：{payload}")
            elif event == "error":
                self.status_var.set("發生錯誤")
                self.start_button.configure(state="normal")
                self._append_log(f"錯誤：{payload}")
                messagebox.showerror("錯誤", str(payload))
            elif event == "auth_error":
                self.auth_button.configure(state="normal")
                self.status_var.set("OAuth 授權失敗")
                self.auth_status_var.set("授權狀態：失敗")
                self._append_log(f"OAuth 授權錯誤：{payload}")
                messagebox.showerror("OAuth 授權錯誤", str(payload))

        self.after(120, self._drain_events)

    def _append_log(self, message: str) -> None:
        self.log_text.insert("end", f"{message}\n")
        self.log_text.see("end")

    def _clear_log(self) -> None:
        self.log_text.delete("1.0", "end")


def main() -> int:
    app = DriveUploaderApp()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
