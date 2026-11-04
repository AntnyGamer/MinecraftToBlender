//go:build windows

package main

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"testing"
)

func TestCancelledPreviewDoesNotStartOrCreateWorkspace(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	workspace := filepath.Join(t.TempDir(), "never-created")
	result := runPreview(ctx, localWorld{}, workspace, "overworld", false, 512, 0, 0)
	if !errors.Is(result.err, context.Canceled) {
		t.Fatalf("cancelled preview should return context.Canceled, got %v", result.err)
	}
	if _, err := os.Stat(workspace); !os.IsNotExist(err) {
		t.Fatalf("cancelled preview must not create workspace: %v", err)
	}
}
