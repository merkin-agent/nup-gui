# Progress & Change Log

This document records meaningful changes and enhancements made to `nup-gui` and its tooling.

## Summary of Changes

1. **Automatic Metadata Discovery & Incorporation**
   - **Technical Explanation**: Enhanced `nup-gui` (`windows_gui.py`) and underlying discovery/packing utilities to automatically scan selected dump folders and `.nup` packages. When a dump folder is selected, it auto-detects application icons via `detect_icon`, infers game titles, and picks up version numbers.

2. **UI Layout Enhancements & Uniform Entry Sizing**
   - **Technical Explanation**: Standardized all `ttk.Entry` fields (`source_entry`, `icon_entry`, `title_entry`, `version_entry`, `publisher_entry`, `output_entry`) to have a uniform width (`width=45`) and height. Relocated the icon row below the title, version, and publisher fields.

3. **Space-Saving Live Icon Thumbnail Preview**
   - **Technical Explanation**: Added a live icon thumbnail preview widget that spans rows 3 to 5 in column 2 (to the right of Game Title, Display Version, and Publisher entry fields), fitting into the interface without increasing row spacing. Traces variable writes on `self.icon` to update dynamically.

4. **Split Metadata Import Buttons & Exact Wording**
   - **Technical Explanation**: Configured three action buttons side-by-side on the same row with exact wording:
     - `"Import from dump"`
     - `"Import from .nup"`
     - `"Import from .nup to .nup"`
   - Implemented field-clearing behavior so fields are reset before importing fresh metadata.

5. **NUP-to-NUP Metadata Copy Dialog Window**
   - **Technical Explanation**: Implemented a dedicated modal window (`tk.Toplevel`) for `"Import from .nup to .nup"` featuring source and target `.nup` file pickers, status updates, and a final `"Copy metadata"` action button leveraging `nup.edit.edit`.

6. **Robust Binary/Text Metadata Validation (`_safe_text`)**
   - **Technical Explanation**: Added strict validation checking during metadata import from NUP packages and dumps to ensure binary image payloads (like JPEG/PNG magic bytes or JFIF headers) are never incorrectly decoded into text fields (title, publisher, display version).

7. **Copy/Paste Context Menus**
   - **Technical Explanation**: Bound right-click context menus (`Cut`, `Copy`, `Paste`, `Select All`) to all editable text entry fields.

8. **Non-Interactive Wine Build Pipeline (`build_wine.sh`)**
   - **Technical Explanation**: Configured `build_wine.sh` to run headlessly under `xvfb-run` with `WINEDLLOVERRIDES="mscoree,mshtml="` to suppress Wine GUI/debugger popups. Applied Python 3.12 `shutil.py` `CopyFile2` bypass for Wine 9 compatibility, enabling reliable, fully non-interactive compilation of `dist/nup-gui.exe` and `dist/nup-gui-windows-x64.zip`.
