//go:build windows

package main

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"syscall"
	"unsafe"
)

var pFinalPathCreateFile = kernel32.NewProc("CreateFileW")
var pFinalPathFromHandle = kernel32.NewProc("GetFinalPathNameByHandleW")
var pFinalPathCloseHandle = kernel32.NewProc("CloseHandle")

// Resolve Windows junctions and directory symlinks using the real filesystem
// handle, since filepath.EvalSymlinks does not resolve every junction target.
func finalPathWindows(path string) (string, error) {
	name, err := syscall.UTF16PtrFromString(path)
	if err != nil {
		return "", err
	}
	const shareAll = 0x1 | 0x2 | 0x4 // FILE_SHARE_READ/WRITE/DELETE
	const openExisting = 3
	const backupSemantics = 0x02000000 // Open directory handles as well as files.
	handle, _, callErr := pFinalPathCreateFile.Call(
		uintptr(unsafe.Pointer(name)),
		0, shareAll, 0, openExisting, backupSemantics, 0,
	)
	if handle == ^uintptr(0) || handle == 0 {
		if callErr == syscall.Errno(2) || callErr == syscall.Errno(3) {
			return "", os.ErrNotExist
		}
		return "", fmt.Errorf("cannot open path for verification %q: %w", path, callErr)
	}
	defer pFinalPathCloseHandle.Call(handle)

	buffer := make([]uint16, 32768)
	n, _, callErr := pFinalPathFromHandle.Call(handle, uintptr(unsafe.Pointer(&buffer[0])), uintptr(len(buffer)), 0)
	if n == 0 || n >= uintptr(len(buffer)) {
		return "", fmt.Errorf("cannot resolve Windows final path %q: %w", path, callErr)
	}
	resolved := syscall.UTF16ToString(buffer[:n])
	const extendedPrefix = "\\\\?\\"
	if strings.HasPrefix(resolved, extendedPrefix+"UNC\\") {
		resolved = "\\\\" + strings.TrimPrefix(resolved, extendedPrefix+"UNC\\")
	} else {
		resolved = strings.TrimPrefix(resolved, extendedPrefix)
	}
	return filepath.Clean(resolved), nil
}
