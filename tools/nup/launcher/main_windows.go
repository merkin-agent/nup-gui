//go:build windows

// NUP Packager's Windows UI is implemented with native Win32 controls. Keeping
// the UI in this executable avoids a PowerShell launcher and its policy/runtime
// dependencies.
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
)

// nup.exe is staged here by the build scripts before the GUI is compiled.
//
//go:embed nup.exe
var nupCLI []byte

const (
	windowClass        = "NUPPackagerWindow"
	wmCreate           = 0x0001
	wmDestroy          = 0x0002
	wmCommand          = 0x0111
	wmClose            = 0x0010
	wmAppDone          = 0x8001
	wsOverlappedWindow = 0x00CF0000
	wsVisible          = 0x10000000
	wsChild            = 0x40000000
	wsTabStop          = 0x00010000
	wsBorder           = 0x00800000
	esAutoHScroll      = 0x0080
	bsPushButton       = 0x00000000
	bsDefPushButton    = 0x00000001
	mbIconError        = 0x00000010
	mbIconInfo         = 0x00000040
	mbOK               = 0x00000000
	cbrowseInfo        = 0x00000051
	bnClicked          = 0
	idSource           = 101
	idOutput           = 102
	idBrowseSource     = 103
	idBrowseOutput     = 104
	idPack             = 105
	idStatus           = 106
	idProgress         = 107
	progressMarquee    = 0x00000008
	progressSetMarquee = 0x040A
	progressStart      = 1
	progressStop       = 0
	ofPathMustExist    = 0x00000800
	ofNoChangeDir      = 0x00000008
	ofOverwritePrompt  = 0x00000002

	colorWindow    = 5
	defaultGuiFont = 17
)

type point struct{ x, y int32 }
type msg struct {
	hwnd, message  uintptr
	wParam, lParam uintptr
	time           uint32
	pt             point
}
type wndClass struct {
	style                              uint32
	proc                               uintptr
	classExtra, windowExtra            int32
	instance, icon, cursor, background uintptr
	menuName, className                *uint16
}
type browseInfo struct {
	owner, root      uintptr
	displayName      *uint16
	title            *uint16
	flags            uint32
	callback, lParam uintptr
	image            int32
}
type openFileName struct {
	size                         uint32
	owner, instance              uintptr
	filter, customFilter         *uint16
	maxCustomFilter, filterIndex uint32
	file                         *uint16
	maxFile                      uint32
	fileTitle                    *uint16
	maxFileTitle                 uint32
	initialDir, title            *uint16
	flags                        uint32
	fileOffset, fileExtension    uint16
	defaultExtension             *uint16
	custData                     uintptr
	hook, templateName           uintptr
	reserved                     uintptr
	reserved2                    uint32
	flagsEx                      uint32
}

var (
	user32                                                       = syscall.NewLazyDLL("user32.dll")
	kernel32                                                     = syscall.NewLazyDLL("kernel32.dll")
	gdi32                                                        = syscall.NewLazyDLL("gdi32.dll")
	shell32                                                      = syscall.NewLazyDLL("shell32.dll")
	comdlg32                                                     = syscall.NewLazyDLL("comdlg32.dll")
	commonControls                                               = syscall.NewLazyDLL("comctl32.dll")
	ole32                                                        = syscall.NewLazyDLL("ole32.dll")
	procDefWindowProc                                            = user32.NewProc("DefWindowProcW")
	procRegisterClass                                            = user32.NewProc("RegisterClassW")
	procCreateWindow                                             = user32.NewProc("CreateWindowExW")
	procShowWindow                                               = user32.NewProc("ShowWindow")
	procUpdateWindow                                             = user32.NewProc("UpdateWindow")
	procGetMessage                                               = user32.NewProc("GetMessageW")
	procTranslateMessage                                         = user32.NewProc("TranslateMessage")
	procDispatchMessage                                          = user32.NewProc("DispatchMessageW")
	procPostQuitMessage                                          = user32.NewProc("PostQuitMessage")
	procPostMessage                                              = user32.NewProc("PostMessageW")
	procSendMessage                                              = user32.NewProc("SendMessageW")
	procSetWindowText                                            = user32.NewProc("SetWindowTextW")
	procGetWindowTextLength                                      = user32.NewProc("GetWindowTextLengthW")
	procGetWindowText                                            = user32.NewProc("GetWindowTextW")
	procMessageBox                                               = user32.NewProc("MessageBoxW")
	procGetSysColorBrush                                         = user32.NewProc("GetSysColorBrush")
	procLoadCursor                                               = user32.NewProc("LoadCursorW")
	procGetModuleHandle                                          = kernel32.NewProc("GetModuleHandleW")
	procGetStockObject                                           = gdi32.NewProc("GetStockObject")
	procBrowseForFolder                                          = shell32.NewProc("SHBrowseForFolderW")
	procGetPathFromID                                            = shell32.NewProc("SHGetPathFromIDListW")
	procCoTaskMemFree                                            = ole32.NewProc("CoTaskMemFree")
	procGetSaveFileName                                          = comdlg32.NewProc("GetSaveFileNameW")
	procInitCommonControls                                       = commonControls.NewProc("InitCommonControls")
	window                                                       uintptr
	sourceEdit, outputEdit, statusLabel, progressBar, packButton uintptr
)

func main() {
	procInitCommonControls.Call()
	instance, _, _ := procGetModuleHandle.Call(0)
	className := mustUTF16(windowClass)
	class := wndClass{
		proc: syscall.NewCallback(windowProc), instance: instance,
		cursor: cursorArrow(), background: func() uintptr { r, _, _ := procGetSysColorBrush.Call(colorWindow); return r }(),
		className: className,
	}
	if atom, _, err := procRegisterClass.Call(uintptr(unsafe.Pointer(&class))); atom == 0 {
		showError("Could not register the application window: " + err.Error())
		return
	}
	title := mustUTF16("NUP Packager")
	window, _, _ = procCreateWindow.Call(0, uintptr(unsafe.Pointer(className)), uintptr(unsafe.Pointer(title)),
		wsOverlappedWindow, 0x80000000, 0x80000000, 780, 270, 0, 0, instance, 0)
	if window == 0 {
		showError("Could not create the application window.")
		return
	}
	procShowWindow.Call(window, 1)
	procUpdateWindow.Call(window)
	var message msg
	for {
		result, _, _ := procGetMessage.Call(uintptr(unsafe.Pointer(&message)), 0, 0, 0)
		if int32(result) <= 0 {
			break
		}
		procTranslateMessage.Call(uintptr(unsafe.Pointer(&message)))
		procDispatchMessage.Call(uintptr(unsafe.Pointer(&message)))
	}
}

func windowProc(hwnd, message, wParam, lParam uintptr) uintptr {
	switch message {
	case wmCreate:
		createUI(hwnd)
		return 0
	case wmCommand:
		if (wParam>>16)&0xffff != bnClicked {
			break
		}
		switch wParam & 0xffff {
		case idBrowseSource:
			browseSource()
		case idBrowseOutput:
			browseOutput()
		case idPack:
			startPacking()
		}
		return 0
	case wmAppDone:
		procSendMessage.Call(progressBar, progressSetMarquee, progressStop, 0)
		procEnableWindow.Call(packButton, 1)
		if wParam == 0 {
			setText(statusLabel, "Package created successfully.")
			showInfo("Created: " + readText(outputEdit))
		} else {
			setText(statusLabel, "Packing failed.")
			showError(fmt.Sprintf("The packer exited with code %d. Check the dump layout and try again.", wParam))
		}
		return 0
	case wmClose:
		procDestroyWindow.Call(hwnd)
		return 0
	case wmDestroy:
		procPostQuitMessage.Call(0)
		return 0
	}
	r, _, _ := procDefWindowProc.Call(hwnd, message, wParam, lParam)
	return r
}

func createUI(hwnd uintptr) {
	label(hwnd, "Dump parent folder", 16, 22, 130, 24)
	sourceEdit = control(hwnd, "EDIT", "", wsBorder|wsTabStop|esAutoHScroll, 150, 18, 500, 28, idSource)
	button(hwnd, "Browse...", 660, 17, 95, 30, idBrowseSource, false)
	label(hwnd, "Output .nup file", 16, 68, 130, 24)
	outputEdit = control(hwnd, "EDIT", "", wsBorder|wsTabStop|esAutoHScroll, 150, 64, 500, 28, idOutput)
	button(hwnd, "Browse...", 660, 63, 95, 30, idBrowseOutput, false)
	statusLabel = control(hwnd, "STATIC", "Choose the dump folder and output file.", 0, 16, 112, 740, 24, idStatus)
	progressBar = control(hwnd, "msctls_progress32", "", progressMarquee, 16, 143, 739, 20, idProgress)
	packButton = button(hwnd, "Create NUP", 635, 180, 120, 34, idPack, true)
	procShowWindow.Call(progressBar, 0)
}

func control(parent uintptr, class, text string, style uint32, x, y, width, height, id int) uintptr {
	classPtr, textPtr := mustUTF16(class), mustUTF16(text)
	instance, _, _ := procGetModuleHandle.Call(0)
	hwnd, _, _ := procCreateWindow.Call(0, uintptr(unsafe.Pointer(classPtr)), uintptr(unsafe.Pointer(textPtr)),
		uintptr(wsChild|wsVisible|style), uintptr(x), uintptr(y), uintptr(width), uintptr(height), parent, uintptr(id), instance, 0)
	font, _, _ := procGetStockObject.Call(defaultGuiFont)
	procSendMessage.Call(hwnd, 0x0030, font, 1)
	return hwnd
}

func label(parent uintptr, text string, x, y, width, height int) uintptr {
	return control(parent, "STATIC", text, 0, x, y, width, height, 0)
}
func button(parent uintptr, text string, x, y, width, height, id int, def bool) uintptr {
	style := uint32(bsPushButton | wsTabStop)
	if def {
		style = bsDefPushButton | wsTabStop
	}
	return control(parent, "BUTTON", text, style, x, y, width, height, id)
}

func browseSource() {
	title := mustUTF16("Choose the folder containing base/, updates/, dlc/, or content folders")
	display := make([]uint16, 260)
	info := browseInfo{owner: window, displayName: &display[0], title: title, flags: cbrowseInfo}
	item, _, _ := procBrowseForFolder.Call(uintptr(unsafe.Pointer(&info)))
	if item == 0 {
		return
	}
	defer procCoTaskMemFree.Call(item)
	path := make([]uint16, 32768)
	if ok, _, _ := procGetPathFromID.Call(item, uintptr(unsafe.Pointer(&path[0]))); ok != 0 {
		setText(sourceEdit, syscall.UTF16ToString(path))
		if readText(outputEdit) == "" {
			selected := syscall.UTF16ToString(path)
			leaf := filepath.Base(filepath.Clean(selected))
			setText(outputEdit, filepath.Join(filepath.Dir(selected), leaf+".nup"))
		}
	}
}

func browseOutput() {
	name := make([]uint16, 32768)
	if current := readText(outputEdit); current != "" {
		chars, _ := syscall.UTF16FromString(current)
		copy(name, chars)
	}
	filter := mustUTF16("NUP package (*.nup)\x00*.nup\x00All files (*.*)\x00*.*\x00\x00")
	title := mustUTF16("Save NUP package")
	ext := mustUTF16("nup")
	dialog := openFileName{size: uint32(unsafe.Sizeof(openFileName{})), owner: window,
		filter: filter, file: &name[0], maxFile: uint32(len(name)), title: title,
		flags: ofPathMustExist | ofNoChangeDir | ofOverwritePrompt, defaultExtension: ext}
	if ok, _, _ := procGetSaveFileName.Call(uintptr(unsafe.Pointer(&dialog))); ok != 0 {
		setText(outputEdit, syscall.UTF16ToString(name))
	}
}

func startPacking() {
	source, output := readText(sourceEdit), readText(outputEdit)
	if source == "" {
		showError("Choose an existing dump parent folder.")
		return
	}
	info, err := os.Stat(source)
	if err != nil || !info.IsDir() {
		showError("Choose an existing dump parent folder.")
		return
	}
	if output == "" {
		showError("Choose where to save the .nup file.")
		return
	}
	if _, err := os.Stat(output); err == nil {
		showError("Choose a new output filename. Existing NUP files are not overwritten.")
		return
	}
	cliPath, err := unpackCLI()
	if err != nil {
		showError(err.Error())
		return
	}
	procEnableWindow.Call(packButton, 0)
	procShowWindow.Call(progressBar, 1)
	procSendMessage.Call(progressBar, progressSetMarquee, progressStart, 25)
	setText(statusLabel, "Packing dump contents. Large dumps may take a while...")
	go func() {
		cmd := exec.Command(cliPath, "pack", source, output)
		cmd.SysProcAttr = &syscall.SysProcAttr{HideWindow: true}
		err := cmd.Run()
		code := uintptr(0)
		if err != nil {
			code = 1
			if exit, ok := err.(*exec.ExitError); ok {
				code = uintptr(exit.ExitCode())
			}
		}
		procPostMessage.Call(window, wmAppDone, code, 0)
	}()
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

func readText(hwnd uintptr) string {
	n, _, _ := procGetWindowTextLength.Call(hwnd)
	buffer := make([]uint16, n+1)
	procGetWindowText.Call(hwnd, uintptr(unsafe.Pointer(&buffer[0])), uintptr(len(buffer)))
	return syscall.UTF16ToString(buffer)
}
func setText(hwnd uintptr, value string) {
	text := mustUTF16(value)
	procSetWindowText.Call(hwnd, uintptr(unsafe.Pointer(text)))
}
func mustUTF16(value string) *uint16 { result, _ := syscall.UTF16PtrFromString(value); return result }
func showError(message string)       { showMessage(message, "NUP Packager", mbIconError) }
func showInfo(message string)        { showMessage(message, "NUP created", mbIconInfo) }
func showMessage(message, title string, icon uintptr) {
	messagePtr, titlePtr := mustUTF16(message), mustUTF16(title)
	procMessageBox.Call(window, uintptr(unsafe.Pointer(messagePtr)), uintptr(unsafe.Pointer(titlePtr)), mbOK|icon)
}
func cursorArrow() uintptr { r, _, _ := procLoadCursor.Call(0, 32512); return r }

var procEnableWindow = user32.NewProc("EnableWindow")
var procDestroyWindow = user32.NewProc("DestroyWindow")
