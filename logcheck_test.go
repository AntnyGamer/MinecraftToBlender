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

func TestProcessCompletionAfterHugeDiagnosticLine(t *testing.T) {
	for _, marker := range []string{blenderImportSuccess, blenderOptimizeSuccess} {
		p := filepath.Join(t.TempDir(), "large.log")
		prefix := strings.Repeat("x", 9*1024*1024)
		if err := os.WriteFile(p, []byte(prefix+"\n"+marker), 0600); err != nil {
			t.Fatal(err)
		}
		if ok, err := confirmedProcessResult(p, marker); err != nil || !ok {
			t.Fatalf("completion after huge diagnostic rejected: %v, %v", ok, err)
		}
		if err := os.WriteFile(p, []byte(prefix), 0600); err != nil {
			t.Fatal(err)
		}
		if ok, err := confirmedProcessResult(p, marker); err != nil || ok {
			t.Fatalf("huge unsuccessful log: %v, %v", ok, err)
		}
		// Move the marker through every possible split at the read boundary.
		for split := 1; split < len(marker); split++ {
			padding := strings.Repeat("x", 64*1024+len(marker)-split)
			if err := os.WriteFile(p, []byte(padding+marker), 0600); err != nil {
				t.Fatal(err)
			}
			if ok, err := confirmedProcessResult(p, marker); err != nil || !ok {
				t.Fatalf("split %d rejected: %v, %v", split, ok, err)
			}
		}
	}
}
