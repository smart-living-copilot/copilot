"""Process lifecycle helpers for isolated execution workers."""

from __future__ import annotations

import os
import signal
import time


def pid_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def terminate_pid(pid: int) -> None:
    if pid <= 0:
        return

    for sig in (signal.SIGTERM, signal.SIGKILL):
        if not pid_is_alive(pid):
            return
        try:
            os.kill(pid, sig)
        except ProcessLookupError:
            return
        except PermissionError:
            return

        deadline = time.monotonic() + (0.5 if sig == signal.SIGTERM else 0)
        while time.monotonic() < deadline:
            if not pid_is_alive(pid):
                return
            time.sleep(0.05)
