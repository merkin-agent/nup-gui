//go:build windows

package main

import (
	"crypto/sha256"
	_ "embed"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"syscall"
	"unsafe"

	"github.com/lxn/walk"
	"github.com/lxn/win"
)

// nup.exe is staged here by the build scripts before the GUI is compiled.
//
//go:embed nup.exe
var nupCLI []byte

const appIconResourceID = 2 // rsrc emits the manifest first, then the icon group.

func main() {
	icon, err := walk.NewIconFromResourceId(appIconResourceID)
	if err != nil {
		showError(nil, "Could not load the application icon: "+err.Error())
		return
	}
	defer icon.Dispose()

	mainWindow, err := walk.NewMainWindow()
	if err != nil {
		showError(nil, "Could not create the packager window: "+err.Error())
		return
	}
	defer mainWindow.Dispose()
	if err := mainWindow.SetTitle("NUP Packager"); err != nil {
		showError(mainWindow, err.Error())
		return
	}
	if err := mainWindow.SetSize(walk.Size{Width: 780, Height: 280}); err != nil {
		showError(mainWindow, err.Error())
		return
	}
	if err := mainWindow.SetIcon(icon); err != nil {
		showError(mainWindow, "Could not apply the application icon: "+err.Error())
		return
	}

	sourceEdit, err := newLineEdit(mainWindow, walk.Rectangle{X: 150, Y: 18, Width: 500, Height: 28})
	if err != nil {
		showError(mainWindow, err.Error())
		return
	}
	outputEdit, err := newLineEdit(mainWindow, walk.Rectangle{X: 150, Y: 64, Width: 500, Height: 28})
	if err != nil {
		showError(mainWindow, err.Error())
		return
	}
	statusLabel, err := newLabel(mainWindow, "Choose the dump folder and output file.", walk.Rectangle{X: 16, Y: 112, Width: 740, Height: 24})
	if err != nil {
		showError(mainWindow, err.Error())
		return
	}
	if _, err = newLabel(mainWindow, "Dump parent folder", walk.Rectangle{X: 16, Y: 22, Width: 130, Height: 24}); err != nil {
		showError(mainWindow, err.Error())
		return
	}
	if _, err = newLabel(mainWindow, "Output .nup file", walk.Rectangle{X: 16, Y: 68, Width: 130, Height: 24}); err != nil {
		showError(mainWindow, err.Error())
		return
	}
	progress, err := walk.NewProgressBar(mainWindow)
	if err != nil {
		showError(mainWindow, err.Error())
		return
	}
	if err := progress.SetBounds(walk.Rectangle{X: 16, Y: 143, Width: 740, Height: 20}); err != nil {
		showError(mainWindow, err.Error())
		return
	}
	if err := progress.SetMarqueeMode(true); err != nil {
		showError(mainWindow, err.Error())
		return
	}
	progress.SetVisible(false)

	var packButton *walk.PushButton
	packButton, err = newButton(mainWindow, "Create NUP", walk.Rectangle{X: 636, Y: 180, Width: 120, Height: 34})
	if err != nil {
		showError(mainWindow, err.Error())
		return
	}
	browseSource, err := newButton(mainWindow, "Browse...", walk.Rectangle{X: 660, Y: 17, Width: 96, Height: 30})
	if err != nil {
		showError(mainWindow, err.Error())
		return
	}
	browseOutput, err := newButton(mainWindow, "Browse...", walk.Rectangle{X: 660, Y: 63, Width: 96, Height: 30})
	if err != nil {
		showError(mainWindow, err.Error())
		return
	}

	browseSource.Clicked().Attach(func() {
		dialog := new(walk.FileDialog)
		dialog.Title = "Choose the folder containing base/, updates/, dlc/, or content folders"
		dialog.InitialDirPath = sourceEdit.Text()
		accepted, err := dialog.ShowBrowseFolder(mainWindow)
		if err != nil {
			showError(mainWindow, "Could not open the folder picker: "+err.Error())
			return
		}
		if !accepted {
			return
		}
		_ = sourceEdit.SetText(dialog.FilePath)
		if outputEdit.Text() == "" {
			leaf := filepath.Base(filepath.Clean(dialog.FilePath))
			_ = outputEdit.SetText(filepath.Join(filepath.Dir(dialog.FilePath), leaf+".nup"))
		}
	})
	browseOutput.Clicked().Attach(func() {
		path, err := savePackageDialog(mainWindow, outputEdit.Text())
		if err != nil {
			showError(mainWindow, "Could not open the save dialog: "+err.Error())
			return
		}
		if path != "" {
			_ = outputEdit.SetText(path)
		}
	})
	packButton.Clicked().Attach(func() {
		startPacking(mainWindow, sourceEdit, outputEdit, statusLabel, progress, packButton)
	})

	mainWindow.Show()
	mainWindow.Run()
}

func newLabel(parent walk.Container, text string, bounds walk.Rectangle) (*walk.Label, error) {
	label, err := walk.NewLabel(parent)
	if err != nil {
		return nil, err
	}
	if err := label.SetText(text); err != nil {
		return nil, err
	}
	if err := label.SetBounds(bounds); err != nil {
		return nil, err
	}
	return label, nil
}

func newLineEdit(parent walk.Container, bounds walk.Rectangle) (*walk.LineEdit, error) {
	edit, err := walk.NewLineEdit(parent)
	if err != nil {
		return nil, err
	}
	if err := edit.SetBounds(bounds); err != nil {
		return nil, err
	}
	return edit, nil
}

func newButton(parent walk.Container, text string, bounds walk.Rectangle) (*walk.PushButton, error) {
	button, err := walk.NewPushButton(parent)
	if err != nil {
		return nil, err
	}
	if err := button.SetText(text); err != nil {
		return nil, err
	}
	if err := button.SetBounds(bounds); err != nil {
		return nil, err
	}
	return button, nil
}

func startPacking(mainWindow *walk.MainWindow, sourceEdit, outputEdit *walk.LineEdit, status *walk.Label, progress *walk.ProgressBar, packButton *walk.PushButton) {
	source, output := sourceEdit.Text(), outputEdit.Text()
	if source == "" {
		showError(mainWindow, "Choose an existing dump parent folder.")
		return
	}
	info, err := os.Stat(source)
	if err != nil || !info.IsDir() {
		showError(mainWindow, "Choose an existing dump parent folder.")
		return
	}
	if output == "" {
		showError(mainWindow, "Choose where to save the .nup file.")
		return
	}
	if _, err := os.Stat(output); err == nil {
		showError(mainWindow, "Choose a new output filename. Existing NUP files are not overwritten.")
		return
	}
	cliPath, err := unpackCLI()
	if err != nil {
		showError(mainWindow, "Could not prepare the packer: "+err.Error())
		return
	}

	packButton.SetEnabled(false)
	progress.SetVisible(true)
	_ = status.SetText("Packing dump contents. Large dumps may take a while...")
	go func() {
		command := exec.Command(cliPath, "pack", source, output)
		command.SysProcAttr = &syscall.SysProcAttr{HideWindow: true}
		err := command.Run()
		mainWindow.Synchronize(func() {
			progress.SetVisible(false)
			packButton.SetEnabled(true)
			if err == nil {
				_ = status.SetText("Package created successfully.")
				walk.MsgBox(mainWindow, "NUP created", "Created:\n"+output, walk.MsgBoxOK|walk.MsgBoxIconInformation)
				return
			}
			_ = status.SetText("Packing failed.")
			message := "The packer could not finish. Check the dump layout and try again."
			if exit, ok := err.(*exec.ExitError); ok {
				message = fmt.Sprintf("The packer exited with code %d. Check the dump layout and try again.", exit.ExitCode())
			}
			showError(mainWindow, message)
		})
	}()
}

func savePackageDialog(owner walk.Form, initialPath string) (string, error) {
	file := make([]uint16, 32768)
	if initialPath != "" {
		copy(file, syscall.StringToUTF16(initialPath))
	}
	filter := syscall.StringToUTF16("NUP package (*.nup)|*.nup|All files (*.*)|*.*|")
	for i, char := range filter {
		if char == '|' {
			filter[i] = 0
		}
	}
	dialog := win.OPENFILENAME{
		LStructSize:  uint32(unsafe.Sizeof(win.OPENFILENAME{})),
		HwndOwner:    owner.Handle(),
		LpstrFilter:  &filter[0],
		NFilterIndex: 1,
		LpstrFile:    &file[0],
		NMaxFile:     uint32(len(file)),
		LpstrTitle:   syscall.StringToUTF16Ptr("Save NUP package"),
		LpstrDefExt:  syscall.StringToUTF16Ptr("nup"),
		Flags:        win.OFN_PATHMUSTEXIST | win.OFN_NOCHANGEDIR | win.OFN_OVERWRITEPROMPT | win.OFN_HIDEREADONLY | win.OFN_EXPLORER,
	}
	if !win.GetSaveFileName(&dialog) {
		if code := win.CommDlgExtendedError(); code != 0 {
			return "", fmt.Errorf("Windows dialog error %d", code)
		}
		return "", nil
	}
	return syscall.UTF16ToString(file), nil
}

func unpackCLI() (string, error) {
	localAppData := os.Getenv("LOCALAPPDATA")
	if localAppData == "" {
		var err error
		localAppData, err = os.UserCacheDir()
		if err != nil {
			return "", err
		}
	}
	digest := sha256.Sum256(nupCLI)
	runtimeDir := filepath.Join(localAppData, "NUPPackager", fmt.Sprintf("%x", digest[:8]))
	if err := os.MkdirAll(runtimeDir, 0o700); err != nil {
		return "", err
	}
	cliPath := filepath.Join(runtimeDir, "nup.exe")
	if _, err := os.Stat(cliPath); err == nil {
		return cliPath, nil
	}
	if err := os.WriteFile(cliPath, nupCLI, 0o700); err != nil {
		return "", err
	}
	return cliPath, nil
}

func showError(owner walk.Form, message string) {
	walk.MsgBox(owner, "NUP Packager", message, walk.MsgBoxOK|walk.MsgBoxIconError)
}
