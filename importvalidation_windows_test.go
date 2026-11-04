//go:build windows

package main

import (
	"context"
	"errors"
	"path/filepath"
	"strings"
	"testing"
)

func TestManualImportStillValidatesUSD(t *testing.T) {
	missing := filepath.Join(t.TempDir(), "missing.usd")
	if _, err := doImport(context.Background(), missing, "", ""); err == nil ||
		!strings.Contains(err.Error(), "USD not found") {
		t.Fatalf("manual import must validate missing USD before attempting Blender: %v", err)
	}
}

func TestCancelledImportCannotStartBlender(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	// Cancellation should win before importer downloads, Blender launch or
	// output-file creation, even if the executable path is invalid.
	_, err := doImportValidated(ctx, "not-a-file.usd", "nonexistent-blender.exe", t.TempDir())
	if !errors.Is(err, context.Canceled) {
		t.Fatalf("cancelled import must return context.Canceled, got %v", err)
	}
}
