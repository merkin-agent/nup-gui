"""Tkinter desktop front end for packing and unpacking NUP dumps."""

from __future__ import annotations

import queue
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from nup.access import extract_dump
from nup.pack import pack
from nup.read import NupReader


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
        self.mode = tk.StringVar(value="pack")
        self.source = tk.StringVar()
        self.output = tk.StringVar()
        self.status = tk.StringVar(value="Choose a dump folder to package.")

        root.title("NUP Packager")
        root.geometry("800x300")
        root.minsize(700, 280)
        root.columnconfigure(1, weight=1)
        root.protocol("WM_DELETE_WINDOW", self.close)
        try:
            root.iconbitmap(str(resource_path(ICON_RELATIVE_PATH)))
        except tk.TclError:
            pass

        self.pack_radio = ttk.Radiobutton(
            root, text="Pack .nup", variable=self.mode, value="pack",
            command=self.update_mode,
        )
        self.pack_radio.grid(row=0, column=0, sticky="w", padx=8, pady=(10, 4))
        self.unpack_radio = ttk.Radiobutton(
            root, text="Unpack .nup", variable=self.mode, value="unpack",
            command=self.update_mode,
        )
        self.unpack_radio.grid(row=0, column=1, sticky="w", padx=8, pady=(10, 4))

        self.source_label = ttk.Label(root)
        self.source_label.grid(row=1, column=0, sticky="w", padx=8, pady=8)
        self.source_entry = ttk.Entry(root, textvariable=self.source)
        self.source_entry.grid(row=1, column=1, sticky="ew", padx=8, pady=8)
        self.source_button = ttk.Button(root, text="Browse...", command=self.browse_source)
        self.source_button.grid(row=1, column=2, sticky="ew", padx=8, pady=8)

        self.output_label = ttk.Label(root)
        self.output_label.grid(row=2, column=0, sticky="w", padx=8, pady=8)
        self.output_entry = ttk.Entry(root, textvariable=self.output)
        self.output_entry.grid(row=2, column=1, sticky="ew", padx=8, pady=8)
        self.output_button = ttk.Button(root, text="Browse...", command=self.browse_output)
        self.output_button.grid(row=2, column=2, sticky="ew", padx=8, pady=8)

        ttk.Label(root, textvariable=self.status).grid(
            row=3, column=0, columnspan=3, sticky="w", padx=8, pady=(10, 4)
        )
        self.progress = ttk.Progressbar(root, mode="indeterminate", maximum=100)
        self.progress.grid(row=4, column=0, columnspan=3, sticky="ew", padx=8, pady=5)
        self.progress.grid_remove()

        self.action_button = ttk.Button(root, command=self.start_operation)
        self.action_button.grid(row=5, column=2, sticky="e", padx=8, pady=10)
        self.update_mode()
        self.root.after(100, self.drain_events)

    def update_mode(self) -> None:
        if self.mode.get() == "pack":
            self.source_label.configure(text="Dump parent folder")
            self.output_label.configure(text="Output .nup file")
            self.action_button.configure(text="Create NUP")
            self.status.set("Choose a dump folder to package.")
        else:
            self.source_label.configure(text="Input .nup file")
            self.output_label.configure(text="Output dump folder")
            self.action_button.configure(text="Extract NUP")
            self.status.set("Choose a .nup file to restore as a dump folder.")

    def browse_source(self) -> None:
        if self.mode.get() == "pack":
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
        else:
            selected = filedialog.askopenfilename(
                parent=self.root,
                title="Choose a NUP package",
                filetypes=(("NUP package", "*.nup"), ("All files", "*.*")),
            )
            if not selected:
                return
            self.source.set(selected)
            if not self.output.get():
                source = Path(selected)
                self.output.set(str(source.parent / source.stem))

    def browse_output(self) -> None:
        if self.mode.get() == "pack":
            selected = filedialog.asksaveasfilename(
                parent=self.root,
                title="Save NUP package",
                initialfile=self.output.get() or "",
                defaultextension=".nup",
                filetypes=(("NUP package", "*.nup"), ("All files", "*.*")),
                confirmoverwrite=False,
            )
        else:
            selected = filedialog.askdirectory(
                parent=self.root,
                title="Choose a parent folder for the restored dump",
                mustexist=True,
            )
            if selected:
                stem = Path(self.source.get()).stem if self.source.get() else "restored"
                selected = str(Path(selected) / stem)
        if selected:
            self.output.set(selected)

    def start_operation(self) -> None:
        source_text = self.source.get().strip()
        output_text = self.output.get().strip()
        if not source_text:
            messagebox.showerror("NUP Packager", "Choose an input first.", parent=self.root)
            return
        if not output_text:
            messagebox.showerror("NUP Packager", "Choose an output location.", parent=self.root)
            return
        source, output = Path(source_text), Path(output_text)
        mode = self.mode.get()
        if mode == "pack":
            if not source.is_dir():
                messagebox.showerror("NUP Packager", "Choose an existing dump folder.", parent=self.root)
                return
            if output.exists():
                messagebox.showerror(
                    "NUP Packager", "Choose a new output filename. Existing files are not overwritten.",
                    parent=self.root,
                )
                return
        else:
            if not source.is_file():
                messagebox.showerror("NUP Packager", "Choose an existing .nup file.", parent=self.root)
                return
            if output.exists() and (not output.is_dir() or any(output.iterdir())):
                messagebox.showerror(
                    "NUP Packager", "Choose a new or empty output folder. Existing files are not overwritten.",
                    parent=self.root,
                )
                return

        self.busy = True
        self._set_controls_enabled(False)
        self.status.set("Scanning dump contents..." if mode == "pack" else "Reading NUP package...")
        self.progress.configure(mode="indeterminate")
        self.progress.grid()
        self.progress.start(12)
        threading.Thread(
            target=self.operation_worker, args=(mode, source, output), daemon=True,
        ).start()

    def operation_worker(self, mode: str, source: Path, output: Path) -> None:
        last_report = 0.0

        def report(done: int, total: int, file_name: str) -> None:
            nonlocal last_report
            now = time.monotonic()
            if now - last_report < 0.1 and done != total:
                return
            last_report = now
            self.events.put(("progress", str(done), str(total), file_name))

        try:
            if mode == "pack":
                pack(str(output), str(source), keep_listings=True, progress=report)
            else:
                with NupReader(str(source)) as reader:
                    extract_dump(reader, str(output), report)
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
                    action = "Packing" if self.mode.get() == "pack" else "Extracting"
                    self.status.set(f"{action} {done} of {total} files: {detail}")
                elif kind == "done":
                    self.finish_operation()
                    action = "Package created" if self.mode.get() == "pack" else "Dump restored"
                    self.status.set(f"{action} successfully.")
                    messagebox.showinfo(action, f"Created:\n{detail}" if self.mode.get() == "pack"
                                        else f"Restored to:\n{detail}", parent=self.root)
                elif kind == "error":
                    self.finish_operation()
                    self.status.set("Operation failed.")
                    messagebox.showerror("NUP operation failed", detail, parent=self.root)
        except queue.Empty:
            pass
        try:
            self.root.after(100, self.drain_events)
        except tk.TclError:
            pass

    def finish_operation(self) -> None:
        self.progress.stop()
        self.progress.grid_remove()
        self.progress_mode = "indeterminate"
        self.busy = False
        self._set_controls_enabled(True)

    def _set_controls_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        for control in (
            self.pack_radio, self.unpack_radio, self.source_entry, self.source_button,
            self.output_entry, self.output_button, self.action_button,
        ):
            control.configure(state=state)

    def close(self) -> None:
        if self.busy:
            messagebox.showwarning(
                "NUP Packager", "Wait for the current operation to finish before closing.",
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
