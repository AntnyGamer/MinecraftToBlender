package main

import (
	"bytes"
	"io"
	"os"
)

const blenderImportSuccess = "RESULT: IMPORT COMPLETED AND BLENDER PROJECT SAVED"
const blenderOptimizeSuccess = "RESULT: EXISTING BLENDER PROJECT OPTIMIZED."

// confirmedBlenderImport scans large Blender logs without loading them all into RAM.
func confirmedBlenderImport(logPath string) (bool, error) {
	return confirmedProcessResult(logPath, blenderImportSuccess)
}

// Search bounded byte blocks with an overlapping tail. Diagnostic lines can
// exceed Scanner's token limit; success markers can also cross read boundaries.
func confirmedProcessResult(logPath, marker string) (bool, error) {
	f, err := os.Open(logPath)
	if err != nil {
		return false, err
	}
	defer f.Close()

	needle := []byte(marker)
	buffer := make([]byte, 64*1024+len(needle))
	tail := 0
	for {
		n, readErr := f.Read(buffer[tail:])
		data := buffer[:tail+n]
		if bytes.Contains(data, needle) {
			return true, nil
		}
		if readErr != nil {
			if readErr == io.EOF {
				return false, nil
			}
			return false, readErr
		}
		tail = min(len(data), len(needle)-1)
		copy(buffer, data[len(data)-tail:])
	}
}
