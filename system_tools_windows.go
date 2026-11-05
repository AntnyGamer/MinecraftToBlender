//go:build windows

package main

import (
	"fmt"
	"path/filepath"
	"strings"
	"syscall"
	"unsafe"
)

var (
	pSystemDirectory  = kernel32.NewProc("GetSystemDirectoryW")
	pWindowsDirectory = kernel32.NewProc("GetSystemWindowsDirectoryW")
)

// Resolve only our built-in Windows helpers. User-selected Blender paths and
// Java discovery keep their existing behavior. Never fall back to PATH for a
// Windows helper: a writable PATH entry could supply a different executable.
func trustedSystemExecutable(name string) (string, error) {
	var directory *syscall.LazyProc
	var relative string
	switch strings.ToLower(name) {
	case "powershell.exe":
		directory, relative = pSystemDirectory, `WindowsPowerShell\v1.0\powershell.exe`
	case "taskkill.exe":
		directory, relative = pSystemDirectory, "taskkill.exe"
	case "explorer.exe":
		directory, relative = pWindowsDirectory, "explorer.exe"
	default:
		return name, nil
	}
	root, err := windowsDirectory(directory)
	if err != nil {
		return "", fmt.Errorf("locate Windows helper %s: %w", name, err)
	}
	return filepath.Join(root, relative), nil
}

func windowsDirectory(proc *syscall.LazyProc) (string, error) {
	buffer := make([]uint16, 260)
	for {
		n, _, callErr := proc.Call(uintptr(unsafe.Pointer(&buffer[0])), uintptr(len(buffer)))
		if n == 0 {
			return "", fmt.Errorf("%s failed: %w", proc.Name, callErr)
		}
		if n < uintptr(len(buffer)) {
			path := syscall.UTF16ToString(buffer[:n])
			if !filepath.IsAbs(path) {
				return "", fmt.Errorf("%s returned a relative directory", proc.Name)
			}
			return path, nil
		}
		if n > 32768 {
			return "", fmt.Errorf("%s returned an invalid directory length", proc.Name)
		}
		buffer = make([]uint16, n+1)
	}
}
