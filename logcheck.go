package main

import (
	"bufio"
	"os"
	"strings"
)

const blenderImportSuccess = "RESULT: IMPORT COMPLETED AND BLENDER PROJECT SAVED"

// confirmedBlenderImport scans large Blender logs without loading them all into RAM.
func confirmedBlenderImport(logPath string) (bool, error) {
	f, err := os.Open(logPath)
	if err != nil {
		return false, err
	}
	defer f.Close()

	scanner := bufio.NewScanner(f)
	scanner.Buffer(make([]byte, 64*1024), 8*1024*1024)
	for scanner.Scan() {
		if strings.Contains(scanner.Text(), blenderImportSuccess) {
			return true, nil
		}
	}
	return false, scanner.Err()
}
