//go:build windows

package main

import (
	"fmt"
	"strings"
	"syscall"
	"unsafe"
)

// Resolve Windows directory junctions and other reparse points using the
// kernel's final path for a handle. filepath.EvalSymlinks alone can leave
// directory junction aliases unresolved on supported Windows installations.
func windowsResolvedExistingPath(path string) (string, error) {
	p, err := syscall.UTF16PtrFromString(path)
	if err != nil {
		return "", err
	}
	handle, err := syscall.CreateFile(p, 0,
		syscall.FILE_SHARE_READ|syscall.FILE_SHARE_WRITE|syscall.FILE_SHARE_DELETE,
		nil, syscall.OPEN_EXISTING, syscall.FILE_FLAG_BACKUP_SEMANTICS, 0)
	if err != nil {
		return "", err
	}
	defer syscall.CloseHandle(handle)

	const bufferLength = 32768
	buffer := make([]uint16, bufferLength)
	proc := kernel32.NewProc("GetFinalPathNameByHandleW")
	length, _, callErr := proc.Call(
		uintptr(handle),
		uintptr(unsafe.Pointer(&buffer[0])),
		uintptr(len(buffer)),
		0,
	)
	if length == 0 || length >= uintptr(len(buffer)) {
		return "", fmt.Errorf("cannot resolve Windows junction %q: %w", path, callErr)
	}
	resolved := syscall.UTF16ToString(buffer[:length])
	switch {
	case strings.HasPrefix(resolved, `\\?\UNC\`):
		return `\\` + strings.TrimPrefix(resolved, `\\?\UNC\`), nil
	case strings.HasPrefix(resolved, `\\?\`):
		return strings.TrimPrefix(resolved, `\\?\`), nil
	default:
		return resolved, nil
	}
}
