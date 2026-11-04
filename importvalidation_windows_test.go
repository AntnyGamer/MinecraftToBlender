//go:build windows

package main

import (
	"context"
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
