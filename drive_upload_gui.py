#!/usr/bin/env python
"""
Traditional Chinese GUI for rclone-backed Google Drive uploads.
"""

from __future__ import annotations

import json
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from rclone_upload import (
    configure_drive_remote,
    find_rclone,
    open_interactive_config,
    remote_exists,
    upload_with_rclone,
)


APP_DIR = Path(__file__).resolve().parent
SETTINGS_PATH = APP_DIR / "gui_settings.json"

CONFLICT_LABELS = {
    "checksum": "用 checksum 判斷，相同略過，不同更新",
    "ignore_existing": "只要同名已存在就略過",
    "force": "不檢查，全部重新上傳",
}
CONFLICT_VALUES = {label: value for value, label in CONFLICT_LABELS.items()}


class DriveUploaderApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Google Drive rclone 上傳工具")
        self.geometry("780x560")
        self.minsize(700, 500)

        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.worker: threading.Thread | None = None
        self.settings = self._load_settings()

        self.rclone_path_var = tk.StringVar(value=self.settings.get("rclone_path", "rclone"))
        self.source_var = tk.StringVar()
        self.remote_name_var = tk.StringVar(value=self.settings.get("remote_name", "gdrive"))
        self.remote_path_var = tk.StringVar(value=self.settings.get("remote_path", ""))
        self.conflict_var = tk.StringVar(value=CONFLICT_LABELS["checksum"])
        self.dry_run_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="尚未開始")
        self.remote_status_var = tk.StringVar(value="rclone 狀態：尚未檢查")
        self.progress_var = tk.DoubleVar(value=0)

        self._build_ui()
        self.after(120, self._drain_events)
        self.after(450, self._check_rclone_status)

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        form = ttk.Frame(self, padding=16)
        form.grid(row=0, column=0, sticky="ew")
        form.columnconfigure(1, weight=1)

        self._path_row(form, 0, "rclone.exe 路徑", self.rclone_path_var, self._choose_rclone)
        self._path_row(form, 1, "來源檔案或資料夾", self.source_var, self._choose_file, self._choose_folder)
        self._entry_row(form, 2, "rclone remote 名稱", self.remote_name_var)
        self._entry_row(form, 3, "Drive 目標路徑（可留空）", self.remote_path_var)

        ttk.Label(form, text="連線狀態").grid(row=4, column=0, sticky="w", pady=6)
        remote_row = ttk.Frame(form)
        remote_row.grid(row=4, column=1, sticky="ew", pady=6)
        remote_row.columnconfigure(0, weight=1)
        ttk.Label(remote_row, textvariable=self.remote_status_var).grid(row=0, column=0, sticky="w")
        ttk.Button(remote_row, text="建立/授權", command=self._configure_remote).grid(row=0, column=1, padx=(8, 0))
        ttk.Button(remote_row, text="互動設定", command=self._open_config).grid(row=0, column=2, padx=(8, 0))

        ttk.Label(form, text="重複檔案處理").grid(row=5, column=0, sticky="w", pady=6)
        conflict = ttk.Combobox(
            form,
            textvariable=self.conflict_var,
            values=list(CONFLICT_VALUES),
            state="readonly",
        )
        conflict.grid(row=5, column=1, sticky="ew", pady=6)

        ttk.Checkbutton(
            form,
            text="只預覽，不實際上傳",
            variable=self.dry_run_var,
        ).grid(row=6, column=1, sticky="w", pady=6)

        actions = ttk.Frame(form)
        actions.grid(row=7, column=1, sticky="e", pady=(10, 0))
        self.start_button = ttk.Button(actions, text="開始上傳", command=self._start_upload)
        self.start_button.grid(row=0, column=0, padx=(0, 8))
        ttk.Button(actions, text="清除紀錄", command=self._clear_log).grid(row=0, column=1)

        output = ttk.Frame(self, padding=(16, 0, 16, 16))
        output.grid(row=1, column=0, sticky="nsew")
        output.columnconfigure(0, weight=1)
        output.rowconfigure(2, weight=1)

        ttk.Label(output, textvariable=self.status_var).grid(row=0, column=0, sticky="w")
        self.progress_bar = ttk.Progressbar(
            output,
            variable=self.progress_var,
            maximum=100,
            mode="indeterminate",
        )
        self.progress_bar.grid(row=1, column=0, sticky="ew", pady=(6, 10))

        self.log_text = tk.Text(output, height=14, wrap="word")
        self.log_text.grid(row=2, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(output, orient="vertical", command=self.log_text.yview)
        scroll.grid(row=2, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=scroll.set)

    def _entry_row(self, parent: ttk.Frame, row: int, label: str, variable: tk.StringVar) -> None:
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

    def _choose_rclone(self) -> None:
        path = filedialog.askopenfilename(
            title="選擇 rclone.exe",
            filetypes=(("rclone", "rclone.exe"), ("執行檔", "*.exe"), ("所有檔案", "*.*")),
        )
        if path:
            self.rclone_path_var.set(path)
            self._save_settings()
            self._check_rclone_status()

    def _choose_file(self) -> None:
        path = filedialog.askopenfilename(title="選擇要上傳的檔案")
        if path:
            self.source_var.set(path)

    def _choose_folder(self) -> None:
        path = filedialog.askdirectory(title="選擇要上傳的資料夾")
        if path:
            self.source_var.set(path)

    def _load_settings(self) -> dict:
        if not SETTINGS_PATH.exists():
            return {}
        try:
            return json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def _save_settings(self) -> None:
        data = {
            "rclone_path": self.rclone_path_var.get().strip(),
            "remote_name": self.remote_name_var.get().strip() or "gdrive",
            "remote_path": self.remote_path_var.get().strip(),
        }
        SETTINGS_PATH.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _resolved_rclone(self) -> str | None:
        value = self.rclone_path_var.get().strip() or "rclone"
        if value.lower() == "rclone":
            return find_rclone()
        return value if Path(value).exists() else None

    def _check_rclone_status(self) -> None:
        rclone_path = self._resolved_rclone()
        if not rclone_path:
            self.remote_status_var.set("rclone 狀態：找不到 rclone.exe")
            self._append_log("找不到 rclone。請先安裝 rclone，或用「瀏覽」選擇 rclone.exe。")
            return

        self.rclone_path_var.set(rclone_path)
        remote_name = self.remote_name_var.get().strip() or "gdrive"
        try:
            if remote_exists(remote_name, rclone_path):
                self.remote_status_var.set(f"rclone 狀態：已找到 remote「{remote_name}:」")
                self._append_log(f"已找到 rclone remote：{remote_name}:")
            else:
                self.remote_status_var.set(f"rclone 狀態：尚未建立 remote「{remote_name}:」")
                self._append_log(f"尚未建立 remote：{remote_name}:，可按「建立/授權」。")
        except RuntimeError as exc:
            self.remote_status_var.set("rclone 狀態：檢查失敗")
            self._append_log(f"rclone 檢查失敗：{exc}")

    def _configure_remote(self) -> None:
        self._run_background("config", self._config_worker)

    def _open_config(self) -> None:
        self._run_background("config", self._interactive_config_worker)

    def _start_upload(self) -> None:
        self._run_background("upload", self._upload_worker)

    def _run_background(self, kind: str, target) -> None:
        if self.worker and self.worker.is_alive():
            messagebox.showinfo("執行中", "目前已有工作正在執行。")
            return
        self._save_settings()
        self.start_button.configure(state="disabled")
        self.progress_bar.start(10)
        self.worker = threading.Thread(target=target, daemon=True)
        self.worker.start()

    def _config_worker(self) -> None:
        try:
            rclone_path = self._required_rclone()
            remote_name = self.remote_name_var.get().strip() or "gdrive"
            self.events.put(("status", "正在建立/授權 rclone Google Drive remote..."))
            summary = configure_drive_remote(
                remote_name,
                rclone_path,
                log=lambda message: self.events.put(("log", message)),
            )
            self.events.put(("config_done", summary.returncode))
        except (OSError, RuntimeError, ValueError) as exc:
            self.events.put(("error", str(exc)))

    def _interactive_config_worker(self) -> None:
        try:
            rclone_path = self._required_rclone()
            self.events.put(("status", "正在開啟 rclone 互動設定..."))
            summary = open_interactive_config(
                rclone_path,
                log=lambda message: self.events.put(("log", message)),
            )
            self.events.put(("config_done", summary.returncode))
        except (OSError, RuntimeError, ValueError) as exc:
            self.events.put(("error", str(exc)))

    def _upload_worker(self) -> None:
        try:
            source = self.source_var.get().strip()
            if not source:
                raise ValueError("請先選擇要上傳的檔案或資料夾。")
            rclone_path = self._required_rclone()
            self.events.put(("status", "正在使用 rclone 上傳..."))
            summary = upload_with_rclone(
                source=Path(source),
                remote_name=self.remote_name_var.get().strip() or "gdrive",
                remote_path=self.remote_path_var.get().strip(),
                conflict_mode=CONFLICT_VALUES[self.conflict_var.get()],
                dry_run=self.dry_run_var.get(),
                rclone_path=rclone_path,
                log=lambda message: self.events.put(("log", message)),
            )
            self.events.put(("upload_done", summary.returncode))
        except (FileNotFoundError, OSError, RuntimeError, ValueError) as exc:
            self.events.put(("error", str(exc)))

    def _required_rclone(self) -> str:
        rclone_path = self._resolved_rclone()
        if not rclone_path:
            raise RuntimeError("找不到 rclone.exe。請先安裝 rclone，或在 GUI 中選擇 rclone.exe。")
        return rclone_path

    def _drain_events(self) -> None:
        while True:
            try:
                event, payload = self.events.get_nowait()
            except queue.Empty:
                break

            if event == "log":
                self._append_log(str(payload))
            elif event == "status":
                self.status_var.set(str(payload))
            elif event == "config_done":
                self._finish_job()
                if payload == 0:
                    self.status_var.set("rclone remote 設定完成")
                    self._check_rclone_status()
                    messagebox.showinfo("完成", "rclone Google Drive remote 設定完成。")
                else:
                    self.status_var.set("rclone remote 設定失敗")
                    messagebox.showerror("錯誤", f"rclone 設定失敗，結束代碼：{payload}")
            elif event == "upload_done":
                self._finish_job()
                if payload == 0:
                    self.status_var.set("上傳完成")
                    messagebox.showinfo("完成", "rclone 上傳流程已完成。")
                else:
                    self.status_var.set("上傳失敗")
                    messagebox.showerror("錯誤", f"rclone 上傳失敗，結束代碼：{payload}")
            elif event == "error":
                self._finish_job()
                self.status_var.set("發生錯誤")
                self._append_log(f"錯誤：{payload}")
                messagebox.showerror("錯誤", str(payload))

        self.after(120, self._drain_events)

    def _finish_job(self) -> None:
        self.progress_bar.stop()
        self.start_button.configure(state="normal")

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
