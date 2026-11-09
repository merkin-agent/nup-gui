"""Tkinter desktop front end for packing and unpacking NUP dumps."""

from __future__ import annotations

import queue
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from nup.errors import OperationCancelled
from nup.icons import detect_icon, is_supported_image
from nup.operations import pack_atomic, unpack_atomic


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
        self.cancel_event: threading.Event | None = None
        self.progress_mode = "indeterminate"
        self.mode = tk.StringVar(value="pack")
        self.source = tk.StringVar()
        self.icon = tk.StringVar()
        self.title_name = tk.StringVar()
        self.display_version = tk.StringVar()
        self.publisher = tk.StringVar()
        self.output = tk.StringVar()
        self.status = tk.StringVar(value="Choose a dump folder to package.")

        root.title("NUP Packager")
        root.geometry("800x440")
        root.minsize(700, 320)
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
        self.source_entry = self.bind_entry(ttk.Entry(root, textvariable=self.source, width=45))
        self.source_entry.grid(row=1, column=1, sticky="ew", padx=8, pady=8)
        self.source_button = ttk.Button(root, text="Browse...", command=self.browse_source)
        self.source_button.grid(row=1, column=2, sticky="ew", padx=8, pady=8)

        # Row 2: Buttons on the same row
        self.buttons_frame = ttk.Frame(root)
        self.buttons_frame.grid(row=2, column=0, columnspan=3, sticky="ew", padx=8, pady=4)
        self.import_dump_button = ttk.Button(self.buttons_frame, text="Import from dump", command=self.import_from_dump)
        self.import_dump_button.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=4)
        self.import_nup_button = ttk.Button(self.buttons_frame, text="Import from .nup", command=self.import_from_nup)
        self.import_nup_button.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=4)
        self.copy_nup_button = ttk.Button(self.buttons_frame, text="Import from .nup to .nup", command=self.copy_metadata_nup_to_nup)
        self.copy_nup_button.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=4)

        self.title_label = ttk.Label(root, text="Game title (optional)")
        self.title_label.grid(row=3, column=0, sticky="w", padx=8, pady=8)
        self.title_entry = self.bind_entry(ttk.Entry(root, textvariable=self.title_name, width=45))
        self.title_entry.grid(row=3, column=1, sticky="ew", padx=8, pady=8)

        self.version_label = ttk.Label(root, text="Display version (optional)")
        self.version_label.grid(row=4, column=0, sticky="w", padx=8, pady=8)
        self.version_entry = self.bind_entry(ttk.Entry(root, textvariable=self.display_version, width=45))
        self.version_entry.grid(row=4, column=1, sticky="ew", padx=8, pady=8)

        self.publisher_label = ttk.Label(root, text="Publisher (optional)")
        self.publisher_label.grid(row=5, column=0, sticky="w", padx=8, pady=8)
        self.publisher_entry = self.bind_entry(ttk.Entry(root, textvariable=self.publisher, width=45))
        self.publisher_entry.grid(row=5, column=1, sticky="ew", padx=8, pady=8)

        # Icon preview spanning rows 3 to 5 in column 2 (to the right of title, version, publisher entries)
        self.icon_preview_label = ttk.Label(root, text="(No Icon)", anchor="center", relief="groove")
        self.icon_preview_label.grid(row=3, column=2, rowspan=3, sticky="nsew", padx=8, pady=4)

        self.icon_label = ttk.Label(root, text="Icon file (optional)")
        self.icon_label.grid(row=6, column=0, sticky="w", padx=8, pady=8)
        self.icon_entry = self.bind_entry(ttk.Entry(root, textvariable=self.icon, width=45))
        self.icon_entry.grid(row=6, column=1, sticky="ew", padx=8, pady=8)
        self.icon_button = ttk.Button(root, text="Browse...", command=self.browse_icon)
        self.icon_button.grid(row=6, column=2, sticky="ew", padx=8, pady=8)

        self.output_label = ttk.Label(root)
        self.output_label.grid(row=7, column=0, sticky="w", padx=8, pady=8)
        self.output_entry = self.bind_entry(ttk.Entry(root, textvariable=self.output, width=45))
        self.output_entry.grid(row=7, column=1, sticky="ew", padx=8, pady=8)
        self.output_button = ttk.Button(root, text="Browse...", command=self.browse_output)
        self.output_button.grid(row=7, column=2, sticky="ew", padx=8, pady=8)

        self.status_label = ttk.Label(root, textvariable=self.status)
        self.status_label.grid(
            row=8, column=0, columnspan=3, sticky="w", padx=8, pady=(10, 4)
        )
        self.progress = ttk.Progressbar(root, mode="indeterminate", maximum=100)
        self.progress.grid(row=9, column=0, columnspan=3, sticky="ew", padx=8, pady=5)
        self.progress.grid_remove()

        self.action_button = ttk.Button(root, command=self.start_operation)
        self.action_button.grid(row=10, column=2, sticky="e", padx=8, pady=10)
        self.cancel_button = ttk.Button(root, text="Cancel", command=self.cancel_operation)
        self.cancel_button.grid(row=10, column=1, sticky="e", padx=8, pady=10)
        self.cancel_button.grid_remove()

        self.icon_image_ref = None
        self.icon.trace_add("write", lambda *_: self.update_icon_preview())
        self.update_mode()
        self.root.after(100, self.drain_events)

    def bind_entry(self, entry: ttk.Entry) -> ttk.Entry:
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label="Cut", command=lambda: entry.event_generate("<<Cut>>"))
        menu.add_command(label="Copy", command=lambda: entry.event_generate("<<Copy>>"))
        menu.add_command(label="Paste", command=lambda: entry.event_generate("<<Paste>>"))
        menu.add_separator()
        menu.add_command(label="Select All", command=lambda: entry.select_range(0, tk.END))

        def show_menu(event: tk.Event) -> None:
            menu.tk_popup(event.x_root, event.y_root)

        entry.bind("<Button-3>", show_menu)
        entry.bind("<Button-2>", show_menu)
        return entry

    def update_icon_preview(self) -> None:
        icon_path = self.icon.get().strip()
        if not icon_path or not os.path.isfile(icon_path):
            self.icon_preview_label.configure(image="", text="(No Icon)")
            self.icon_image_ref = None
            return
        try:
            img = tk.PhotoImage(file=icon_path)
            w, h = img.width(), img.height()
            if w > 48 or h > 48:
                factor = max(w // 48, h // 48, 1)
                img = img.subsample(factor, factor)
            self.icon_preview_label.configure(image=img, text="")
            self.icon_image_ref = img
        except Exception:
            self.icon_preview_label.configure(image="", text="(Icon)")
            self.icon_image_ref = None

    def update_mode(self) -> None:
        if self.mode.get() == "pack":
            for widget in (self.buttons_frame,
                           self.icon_preview_label,
                           self.icon_label, self.icon_entry, self.icon_button,
                           self.title_label, self.title_entry,
                           self.version_label, self.version_entry,
                           self.publisher_label, self.publisher_entry):
                widget.grid()
            self.output_label.grid(row=7, column=0, sticky="w", padx=8, pady=8)
            self.output_entry.grid(row=7, column=1, sticky="ew", padx=8, pady=8)
            self.output_button.grid(row=7, column=2, sticky="ew", padx=8, pady=8)
            self.status_label.grid(row=8, column=0, columnspan=3,
                                   sticky="w", padx=8, pady=(10, 4))
            self.progress.grid(row=9, column=0, columnspan=3, sticky="ew", padx=8, pady=5)
            self.progress.grid_remove()
            self.action_button.grid(row=10, column=2, sticky="e", padx=8, pady=10)
            self.cancel_button.grid(row=10, column=1, sticky="e", padx=8, pady=10)
            self.cancel_button.grid_remove()
            self.root.geometry("800x480")
            self.source_label.configure(text="Dump parent folder")
            self.output_label.configure(text="Output .nup file")
            self.action_button.configure(text="Create NUP")
            self.status.set("Choose a dump folder to package.")
        else:
            for widget in (self.buttons_frame,
                           self.icon_preview_label,
                           self.icon_label, self.icon_entry, self.icon_button,
                           self.title_label, self.title_entry,
                           self.version_label, self.version_entry,
                           self.publisher_label, self.publisher_entry):
                widget.grid_remove()
            self.output_label.grid(row=2, column=0, sticky="w", padx=8, pady=8)
            self.output_entry.grid(row=2, column=1, sticky="ew", padx=8, pady=8)
            self.output_button.grid(row=2, column=2, sticky="ew", padx=8, pady=8)
            self.status_label.grid(row=3, column=0, columnspan=3,
                                   sticky="w", padx=8, pady=(10, 4))
            self.progress.grid(row=4, column=0, columnspan=3, sticky="ew", padx=8, pady=5)
            self.progress.grid_remove()
            self.action_button.grid(row=5, column=2, sticky="e", padx=8, pady=10)
            self.cancel_button.grid(row=5, column=1, sticky="e", padx=8, pady=10)
            self.cancel_button.grid_remove()
            self.root.geometry("800x280")
            self.source_label.configure(text="Input .nup file")
            self.output_label.configure(text="Output dump folder")
            self.action_button.configure(text="Extract NUP")
            self.status.set("Choose a .nup file to restore as a dump folder.")

    def import_from_nup(self) -> None:
        selected = filedialog.askopenfilename(
            parent=self.root,
            title="Choose a NUP package to import metadata from",
            filetypes=(("NUP package", "*.nup"), ("All files", "*.*")),
        )
        if not selected:
            return
        path = Path(selected)

        # Clear fields before importing
        self.title_name.set("")
        self.publisher.set("")
        self.display_version.set("")
        self.icon.set("")

        try:
            from nup import format as F
            from nup.access import meta_records
            from nup.read import NupReader
            import tempfile
            import os

            def _safe_text(payload: bytes | None) -> str | None:
                if not payload:
                    return None
                try:
                    text = payload.decode("utf-8", "strict")
                    if any(ord(c) < 32 and c not in "\t\n\r" for c in text) or len(text) > 256 or text.startswith(("\xff\xd8", "\x89PNG", "JFIF")):
                        return None
                    return text
                except UnicodeDecodeError:
                    return None

            def _find_meta_package(r):
                base_pkg = next((p for p in r.packages if p.kind == F.KIND_BASE), None)
                if base_pkg and base_pkg.meta_size:
                    m = dict(meta_records(r, base_pkg))
                    if any(t in m for t in (F.TLV_TITLE_NAME, F.TLV_PUBLISHER, F.TLV_DISPLAY_VERSION, F.TLV_ICON)):
                        return base_pkg, m
                for p in r.packages:
                    if p.meta_size:
                        m = dict(meta_records(r, p))
                        if any(t in m for t in (F.TLV_TITLE_NAME, F.TLV_PUBLISHER, F.TLV_DISPLAY_VERSION, F.TLV_ICON)):
                            return p, m
                if r.packages:
                    p = r.packages[0]
                    return p, dict(meta_records(r, p)) if p.meta_size else {}
                return None, {}

            imported = []
            with NupReader(str(path)) as reader:
                _, meta = _find_meta_package(reader)
                t_text = _safe_text(meta.get(F.TLV_TITLE_NAME))
                if t_text:
                    self.title_name.set(t_text)
                    imported.append(f"title: {t_text}")
                p_text = _safe_text(meta.get(F.TLV_PUBLISHER))
                if p_text:
                    self.publisher.set(p_text)
                    imported.append(f"publisher: {p_text}")
                v_text = _safe_text(meta.get(F.TLV_DISPLAY_VERSION))
                if v_text:
                    self.display_version.set(v_text)
                    imported.append(f"version: {v_text}")
                icon_data = meta.get(F.TLV_ICON)
                if icon_data:
                    ext = image_extension(icon_data) or ".png"
                    tmp_fd, tmp_path = tempfile.mkstemp(suffix=ext, prefix="nup-import-icon-")
                    os.close(tmp_fd)
                    Path(tmp_path).write_bytes(icon_data)
                    if is_supported_image(tmp_path):
                        self.icon.set(tmp_path)
                        imported.append(f"icon from {path.name}")
            if imported:
                self.status.set(f"Successfully imported metadata from {path.name}: {', '.join(imported)}")
            else:
                self.status.set(f"No valid application metadata found in {path.name}.")
        except Exception as exc:
            messagebox.showerror("Import Failed", f"Could not import metadata from {path.name}:\n{exc}", parent=self.root)

    def import_from_dump(self) -> None:
        selected_dir = filedialog.askdirectory(
            parent=self.root,
            title="Choose a dump folder to import metadata from",
            mustexist=True,
        )
        if selected_dir:
            self.auto_populate_metadata(Path(selected_dir))
            self.status.set(f"Imported metadata from dump folder: {selected_dir}")

    def copy_metadata_nup_to_nup(self) -> None:
        dlg = tk.Toplevel(self.root)
        dlg.title("Import from .nup to .nup")
        dlg.geometry("650x240")
        dlg.minsize(600, 220)
        dlg.transient(self.root)
        dlg.grab_set()
        dlg.columnconfigure(1, weight=1)

        src_var = tk.StringVar()
        dst_var = tk.StringVar()

        ttk.Label(dlg, text="Source .nup file:").grid(row=0, column=0, sticky="w", padx=10, pady=10)
        src_entry = self.bind_entry(ttk.Entry(dlg, textvariable=src_var, width=45))
        src_entry.grid(row=0, column=1, sticky="ew", padx=10, pady=10)
        ttk.Button(dlg, text="Browse...", command=lambda: src_var.set(filedialog.askopenfilename(parent=dlg, title="Choose Source .nup", filetypes=(("NUP package", "*.nup"), ("All files", "*.*"))))).grid(row=0, column=2, padx=10, pady=10)

        ttk.Label(dlg, text="Target .nup file:").grid(row=1, column=0, sticky="w", padx=10, pady=10)
        dst_entry = self.bind_entry(ttk.Entry(dlg, textvariable=dst_var, width=45))
        dst_entry.grid(row=1, column=1, sticky="ew", padx=10, pady=10)
        ttk.Button(dlg, text="Browse...", command=lambda: dst_var.set(filedialog.askopenfilename(parent=dlg, title="Choose Target .nup", filetypes=(("NUP package", "*.nup"), ("All files", "*.*"))))).grid(row=1, column=2, padx=10, pady=10)

        status_v = tk.StringVar(value="Select source and target .nup files, then click Copy metadata.")
        ttk.Label(dlg, textvariable=status_v).grid(row=2, column=0, columnspan=3, sticky="w", padx=10, pady=(5, 10))

        def execute_copy() -> None:
            s_path = src_var.get().strip()
            d_path = dst_var.get().strip()
            if not s_path or not os.path.isfile(s_path):
                messagebox.showerror("Error", "Please select a valid source .nup file.", parent=dlg)
                return
            if not d_path or not os.path.isfile(d_path):
                messagebox.showerror("Error", "Please select a valid target .nup file.", parent=dlg)
                return
            try:
                from nup import format as F
                from nup.access import meta_records
                from nup.edit import edit
                from nup.read import NupReader
                import tempfile
                import os

                def _safe_text(payload: bytes | None) -> str | None:
                    if not payload:
                        return None
                    try:
                        text = payload.decode("utf-8", "strict")
                        if any(ord(c) < 32 and c not in "\t\n\r" for c in text) or len(text) > 256 or text.startswith(("\xff\xd8", "\x89PNG", "JFIF")):
                            return None
                        return text
                    except UnicodeDecodeError:
                        return None

                def _find_meta_package(r):
                    base_pkg = next((p for p in r.packages if p.kind == F.KIND_BASE), None)
                    if base_pkg and base_pkg.meta_size:
                        m = dict(meta_records(r, base_pkg))
                        if any(t in m for t in (F.TLV_TITLE_NAME, F.TLV_PUBLISHER, F.TLV_DISPLAY_VERSION, F.TLV_ICON)):
                            return base_pkg, m
                    for p in r.packages:
                        if p.meta_size:
                            m = dict(meta_records(r, p))
                            if any(t in m for t in (F.TLV_TITLE_NAME, F.TLV_PUBLISHER, F.TLV_DISPLAY_VERSION, F.TLV_ICON)):
                                return p, m
                    if r.packages:
                        p = r.packages[0]
                        return p, dict(meta_records(r, p)) if p.meta_size else {}
                    return None, {}

                title, pub, ver, icon_path = None, None, None, None
                with NupReader(s_path) as reader:
                    _, meta = _find_meta_package(reader)
                    title = _safe_text(meta.get(F.TLV_TITLE_NAME))
                    pub = _safe_text(meta.get(F.TLV_PUBLISHER))
                    ver = _safe_text(meta.get(F.TLV_DISPLAY_VERSION))
                    icon_data = meta.get(F.TLV_ICON)
                    if icon_data:
                        ext = image_extension(icon_data) or ".png"
                        tmp_fd, tmp_path = tempfile.mkstemp(suffix=ext, prefix="nup-copy-icon-")
                        os.close(tmp_fd)
                        Path(tmp_path).write_bytes(icon_data)
                        if is_supported_image(tmp_path):
                            icon_path = tmp_path

                edit(d_path, name=title, publisher=pub, display_version=ver, icon=icon_path)
                status_v.set(f"Successfully copied metadata to {Path(d_path).name}!")
                messagebox.showinfo("Success", f"Metadata copied successfully to:\n{d_path}", parent=dlg)
                dlg.destroy()
            except Exception as exc:
                messagebox.showerror("Copy Failed", f"Could not copy metadata between NUP files:\n{exc}", parent=dlg)

        copy_btn = ttk.Button(dlg, text="Copy metadata", command=execute_copy)
        copy_btn.grid(row=3, column=2, sticky="e", padx=10, pady=10)

    def browse_icon(self) -> None:
        selected = filedialog.askopenfilename(
            parent=self.root,
            title="Choose an application icon",
            filetypes=(("JPEG or PNG image", "*.jpg *.jpeg *.png *.dat"),
                       ("All files", "*.*")),
        )
        if selected:
            if not is_supported_image(selected):
                messagebox.showerror(
                    "Invalid Format",
                    "The selected file is not a supported JPEG or PNG image format (missing valid magic bytes).",
                    parent=self.root,
                )
                return
            self.icon.set(selected)

    def auto_populate_metadata(self, source_path: Path) -> None:
        self.title_name.set("")
        self.publisher.set("")
        self.display_version.set("")
        self.icon.set("")
        try:
            from nup import format as F
            from nup.discover import discover
            from nup.icons import detect_icon
            packages = discover(str(source_path), None)
            found: list[str] = []
            if packages:
                detected = detect_icon(str(source_path), [p.src for p in packages])
                if detected and is_supported_image(detected):
                    self.icon.set(detected)
                    found.append(f"icon: {Path(detected).name}")
                self.title_name.set(source_path.name)
                found.append(f"title: {source_path.name}")
                base_pkg = next((p for p in packages if p.kind == F.KIND_BASE), packages[0])
                if base_pkg and base_pkg.version > 0:
                    v = base_pkg.version
                    ver_str = f"{v >> 16}.{(v >> 8) & 0xFF}.{v & 0xFF}"
                    if ver_str != "0.0.0":
                        self.display_version.set(ver_str)
                        found.append(f"version: {ver_str}")
            if found:
                self.status.set(f"Found metadata from dump: {', '.join(found)}. You can manually edit or replace any item.")
            else:
                self.status.set("Pack mode ready. Review or manually edit metadata items below.")
        except (Exception, SystemExit) as exc:
            self.status.set(f"Pack mode ready (metadata scan warning: {exc})")

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
            source = Path(selected)
            if not self.output.get():
                self.output.set(str(source.parent / f"{source.name}.nup"))
            self.auto_populate_metadata(source)
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
            self.auto_populate_metadata(source)
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
            if output.exists():
                messagebox.showerror(
                    "NUP Packager", "Choose a new output folder. Existing folders are not overwritten.",
                    parent=self.root,
                )
                return

        self.busy = True
        self.cancel_event = threading.Event()
        self._set_controls_enabled(False)
        self.cancel_button.configure(text="Cancel", state="normal")
        self.cancel_button.grid()
        self.status.set("Scanning dump contents..." if mode == "pack" else "Reading NUP package...")
        self.progress.configure(mode="indeterminate")
        self.progress.grid()
        self.progress.start(12)
        threading.Thread(
            target=self.operation_worker,
            args=(mode, source, output, self.cancel_event,
                  self.icon.get().strip() or None,
                  self.title_name.get().strip() or None,
                  self.display_version.get().strip() or None,
                  self.publisher.get().strip() or None), daemon=True,
        ).start()

    def cancel_operation(self) -> None:
        if self.cancel_event is None or self.cancel_event.is_set():
            return
        self.cancel_event.set()
        self.cancel_button.configure(text="Cancelling...", state="disabled")
        self.status.set("Cancelling at the next safe checkpoint and removing temporary output...")

    def operation_worker(
        self,
        mode: str,
        source: Path,
        output: Path,
        cancel_event: threading.Event,
        icon: str | None,
        title_name: str | None,
        display_version: str | None,
        publisher: str | None,
    ) -> None:
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
                def pack_progress(done: int, total: int, file_node: object) -> None:
                    raw_name = getattr(file_node, "name", b"")
                    name = raw_name.decode("utf-8", "replace") if isinstance(raw_name, bytes) else str(raw_name)
                    report(done, total, name)

                pack_atomic(
                    str(output), str(source), keep_listings=True,
                    icon=icon, name=title_name, display_version=display_version,
                    publisher=publisher,
                    progress=pack_progress, cancel=cancel_event.is_set,
                )
            else:
                unpack_atomic(
                    str(source), str(output), progress=report,
                    cancel=cancel_event.is_set,
                )
        except OperationCancelled:
            self.events.put(("cancelled", "", "", str(output)))
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
                elif kind == "cancelled":
                    self.finish_operation()
                    self.status.set("Cancelled. Temporary output removed; original files are unchanged.")
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
        self.cancel_event = None
        self.cancel_button.configure(text="Cancel", state="disabled")
        self.cancel_button.grid_remove()
        self._set_controls_enabled(True)

    def _set_controls_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        for control in (
            self.pack_radio, self.unpack_radio, self.source_entry, self.source_button,
            self.import_nup_button, self.import_dump_button, self.copy_nup_button,
            self.icon_entry, self.icon_button, self.title_entry, self.version_entry,
            self.publisher_entry,
            self.output_entry, self.output_button, self.action_button,
        ):
            control.configure(state=state)
        self.cancel_button.configure(state="disabled" if enabled else "normal")

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
