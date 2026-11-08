"""Windows-runner smoke check for NUP Packager's Tk event loop."""

from __future__ import annotations

import ctypes
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: smoke_gui.py path/to/nup-gui.exe")

    executable = Path(sys.argv[1]).resolve()
    process = subprocess.Popen([str(executable)])
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.FindWindowW.argtypes = (wintypes.LPCWSTR, wintypes.LPCWSTR)
    user32.FindWindowW.restype = wintypes.HWND
    user32.IsHungAppWindow.argtypes = (wintypes.HWND,)
    user32.IsHungAppWindow.restype = wintypes.BOOL
    user32.EnumChildWindows.argtypes = (wintypes.HWND, ctypes.c_void_p, wintypes.LPARAM)
    user32.EnumChildWindows.restype = wintypes.BOOL
    user32.PostMessageW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
    user32.PostMessageW.restype = wintypes.BOOL

    hwnd = None
    deadline = time.monotonic() + 15
    try:
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError(f"GUI exited during startup with code {process.returncode}")
            hwnd = user32.FindWindowW(None, "NUP Packager")
            if hwnd:
                break
            time.sleep(0.1)

        if not hwnd:
            raise RuntimeError("GUI window did not appear within 15 seconds")
        if user32.IsHungAppWindow(hwnd):
            raise RuntimeError("GUI window is not processing Windows messages")
        children: list[int] = []
        callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        callback = callback_type(lambda child, _data: children.append(child) or True)
        user32.EnumChildWindows(hwnd, callback, 0)
        if len(children) < 5:
            raise RuntimeError(f"GUI opened with only {len(children)} child controls")

        if not user32.PostMessageW(hwnd, 0x0010, 0, 0):  # WM_CLOSE
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("GUI did not close in response to WM_CLOSE") from exc
        if process.returncode != 0:
            raise RuntimeError(f"GUI exited with code {process.returncode} after WM_CLOSE")
        print("Tk GUI opened, responded to Windows messages, and closed cleanly.")
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == "__main__":
    main()
