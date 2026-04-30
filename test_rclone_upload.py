import sys
import threading
import time
import unittest

from rclone_upload import RCLONE_CANCELLED_RETURN_CODE, _run_streaming


class RcloneStreamingTests(unittest.TestCase):
    def test_run_streaming_can_cancel_running_process(self) -> None:
        cancel_event = threading.Event()
        logs: list[str] = []
        command = [
            sys.executable,
            "-c",
            "import time; print('started', flush=True); time.sleep(30)",
        ]

        def cancel_after_start() -> None:
            deadline = time.monotonic() + 5
            while "started" not in logs and time.monotonic() < deadline:
                time.sleep(0.02)
            cancel_event.set()

        timer = threading.Thread(target=cancel_after_start)
        timer.start()
        started_at = time.monotonic()
        summary = _run_streaming(command, logs.append, cancel_event=cancel_event)
        elapsed = time.monotonic() - started_at
        timer.join(timeout=1)

        self.assertEqual(RCLONE_CANCELLED_RETURN_CODE, summary.returncode)
        self.assertLess(elapsed, 10)
        self.assertIn("started", logs)
        self.assertTrue(any("取消" in line for line in logs))


if __name__ == "__main__":
    unittest.main()
