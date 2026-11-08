//go:build windows

package main

import (
	"crypto/sha256"
	_ "embed"
	"encoding/base64"
	"encoding/binary"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"syscall"
	"unicode/utf16"
	"unsafe"
)

// nup.exe is staged here by build_wine.sh before the GUI is compiled.
//
//go:embed nup.exe
var nupCLI []byte

//go:embed gui.ps1
var guiScript string

func main() {
	cliPath, err := unpackCLI()
	if err != nil {
		showError("NUP Packager", err.Error())
		return
	}
	encodedScript, err := encodePowerShell(guiScript)
	if err != nil {
		showError("NUP Packager", err.Error())
		return
	}
	command := exec.Command("powershell.exe", "-NoLogo", "-NoProfile", "-STA",
		"-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-EncodedCommand", encodedScript)
	command.Env = append(os.Environ(), "NUP_CLI_PATH="+cliPath)
	command.SysProcAttr = &syscall.SysProcAttr{HideWindow: true}
	if err := command.Run(); err != nil {
		showError("NUP Packager", fmt.Sprintf("Could not open the packager window: %v", err))
	}
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

func encodePowerShell(script string) (string, error) {
	wide := utf16.Encode([]rune(script))
	bytes := make([]byte, len(wide)*2)
	for i, codeUnit := range wide {
		binary.LittleEndian.PutUint16(bytes[i*2:], codeUnit)
	}
	return base64.StdEncoding.EncodeToString(bytes), nil
}

var (
	user32           = syscall.NewLazyDLL("user32.dll")
	messageBoxW      = user32.NewProc("MessageBoxW")
	utf16PtrFromText = syscall.UTF16PtrFromString
)

func showError(title, message string) {
	titlePtr, _ := utf16PtrFromText(title)
	messagePtr, _ := utf16PtrFromText(message)
	messageBoxW.Call(0, uintptr(unsafePointer(messagePtr)), uintptr(unsafePointer(titlePtr)), 0x10)
}

func unsafePointer(value *uint16) unsafe.Pointer {
	return unsafe.Pointer(value)
}
