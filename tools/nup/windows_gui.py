"""Tkinter desktop front end for the NUP packer."""

from __future__ import annotations

import queue
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from nup.pack import pack


ICON_RELATIVE_PATH = Path("assets") / "NUP_GUI_Packager.ico"


def resource_path(relative_path: Path) -> Path:
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        return Path(frozen_root) / relative_path
    return Path(__file__).resolve().parent / "launcher" / relative_path


class NupPackagerApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.events: queue.Queue[tuple[str, str, str, str]] = queue.Queue()
        self.busy = False
        self.progress_mode = "indeterminate"

        root.title("NUP Packager")
        root.geometry("780x250")
        root.minsize(700, 230)
        root.columnconfigure(1, weight=1)
        root.protocol("WM_DELETE_WINDOW", self.close)
        try:
            root.iconbitmap(str(resource_path(ICON_RELATIVE_PATH)))
        except tk.TclError:
            pass

        self.source = tk.StringVar()
        self.output = tk.StringVar()
        self.status = tk.StringVar(value="Choose the dump folder and output file.")

        padding = {"padx": 8, "pady": 8}
        ttk.Label(root, text="Dump parent folder").grid(row=0, column=0, sticky="w", **padding)
        self.source_entry = ttk.Entry(root, textvariable=self.source)
        self.source_entry.grid(row=0, column=1, sticky="ew", **padding)
        self.source_button = ttk.Button(root, text="Browse...", command=self.browse_source)
        self.source_button.grid(row=0, column=2, sticky="ew", **padding)

        ttk.Label(root, text="Output .nup file").grid(row=1, column=0, sticky="w", **padding)
        self.output_entry = ttk.Entry(root, textvariable=self.output)
        self.output_entry.grid(row=1, column=1, sticky="ew", **padding)
        self.output_button = ttk.Button(root, text="Browse...", command=self.browse_output)
        self.output_button.grid(row=1, column=2, sticky="ew", **padding)

        ttk.Label(root, textvariable=self.status).grid(
            row=2, column=0, columnspan=3, sticky="w", padx=8, pady=(10, 4)
        )
        self.progress = ttk.Progressbar(root, mode="indeterminate", maximum=100)
        self.progress.grid(row=3, column=0, columnspan=3, sticky="ew", padx=8, pady=5)
        self.progress.grid_remove()

        self.pack_button = ttk.Button(root, text="Create NUP", command=self.start_pack)
        self.pack_button.grid(row=4, column=2, sticky="e", padx=8, pady=10)

        self.root.after(100, self.drain_events)

    def browse_source(self) -> None:
        options = {
            "parent": self.root,
            "title": "Choose the folder containing base/, updates/, dlc/, or content folders",
            "mustexist": True,
        }
        if self.source.get():
            options["initialdir"] = self.source.get()
        selected = filedialog.askdirectory(**options)
        if not selected:
            return
        self.source.set(selected)
        if not self.output.get():
            source = Path(selected)
            self.output.set(str(source.parent / f"{source.name}.nup"))

    def browse_output(self) -> None:
        selected = filedialog.asksaveasfilename(
            parent=self.root,
            title="Save NUP package",
            initialfile=self.output.get() or "",
            defaultextension=".nup",
            filetypes=(("NUP package", "*.nup"), ("All files", "*.*")),
            confirmoverwrite=False,
        )
        if selected:
            self.output.set(selected)

    def start_pack(self) -> None:
        source_text = self.source.get().strip()
        output_text = self.output.get().strip()
        if not source_text or not Path(source_text).is_dir():
            messagebox.showerror("NUP Packager", "Choose an existing dump parent folder.", parent=self.root)
            return
        if not output_text:
            messagebox.showerror("NUP Packager", "Choose where to save the .nup file.", parent=self.root)
            return
        source = Path(source_text)
        output = Path(output_text)
        if output.exists():
            messagebox.showerror(
                "NUP Packager",
                "Choose a new output filename. Existing NUP files are not overwritten.",
                parent=self.root,
            )
            return

        self.busy = True
        self._set_controls_enabled(False)
        self.status.set("Scanning dump contents...")
        self.progress.configure(mode="indeterminate")
        self.progress.grid()
        self.progress.start(12)
        threading.Thread(target=self.pack_worker, args=(source, output), daemon=True).start()

    def pack_worker(self, source: Path, output: Path) -> None:
        last_report = 0.0

        def report(done: int, total: int, file_node: object) -> None:
            nonlocal last_report
            now = time.monotonic()
            if now - last_report < 0.1 and done != total:
                return
            last_report = now
            raw_name = getattr(file_node, "name", b"")
            detail = raw_name.decode("utf-8", "replace") if isinstance(raw_name, bytes) else str(raw_name)
            self.events.put(("progress", str(done), str(total), detail))

        try:
            pack(str(output), str(source), progress=report)
        except (Exception, SystemExit) as exc:
            self.events.put(("error", "", "", f"{type(exc).__name__}: {exc}"))
        else:
            self.events.put(("done", "", "", str(output)))

    def drain_events(self) -> None:
        try:
            while True:
                kind, first, second, detail = self.events.get_nowait()
                if kind == "progress":
                    done, total = int(first), int(second)
                    if self.progress_mode != "determinate":
                        self.progress.stop()
                        self.progress.configure(mode="determinate")
                        self.progress_mode = "determinate"
                    self.progress.configure(maximum=max(1, total), value=done)
                    suffix = f": {detail}" if detail else ""
                    self.status.set(f"Packing {done} of {total} files{suffix}")
                elif kind == "done":
                    self.finish_pack()
                    self.status.set("Package created successfully.")
                    messagebox.showinfo("NUP created", f"Created:\n{detail}", parent=self.root)
                elif kind == "error":
                    self.finish_pack()
                    self.status.set("Packing failed.")
                    messagebox.showerror("Packing failed", detail, parent=self.root)
        except queue.Empty:
            pass
        try:
            self.root.after(100, self.drain_events)
        except tk.TclError:
            pass

    def finish_pack(self) -> None:
        self.progress.stop()
        self.progress.grid_remove()
        self.progress_mode = "indeterminate"
        self.busy = False
        self._set_controls_enabled(True)

    def _set_controls_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        for control in (self.source_entry, self.source_button, self.output_entry, self.output_button, self.pack_button):
            control.configure(state=state)

    def close(self) -> None:
        if self.busy:
            messagebox.showwarning(
                "NUP Packager",
                "Packing is still in progress. Wait for it to finish before closing the window.",
                parent=self.root,
            )
            return
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    NupPackagerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
