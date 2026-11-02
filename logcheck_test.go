package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestConfirmedBlenderImport(t *testing.T) {
	p := filepath.Join(t.TempDir(), "Blender_import.log")
	if ok, err := confirmedBlenderImport(p); ok || !os.IsNotExist(err) {
		t.Fatalf("missing file: ok=%v err=%v", ok, err)
	}
	// A large, unsuccessful log must not cause a false success or load fully into memory.
	if err := os.WriteFile(p, []byte(strings.Repeat("some error details\n", 220000)), 0600); err != nil {
		t.Fatal(err)
	}
	if ok, err := confirmedBlenderImport(p); err != nil || ok {
		t.Fatalf("false success: ok=%v err=%v", ok, err)
	}
	f, err := os.OpenFile(p, os.O_APPEND|os.O_WRONLY, 0600)
	if err != nil {
		t.Fatal(err)
	}
	_, err = f.WriteString(blenderImportSuccess + "\n")
	closeErr := f.Close()
	if err != nil {
		t.Fatal(err)
	}
	if closeErr != nil {
		t.Fatal(closeErr)
	}
	if ok, err := confirmedBlenderImport(p); err != nil || !ok {
		t.Fatalf("valid result rejected: ok=%v err=%v", ok, err)
	}
}
