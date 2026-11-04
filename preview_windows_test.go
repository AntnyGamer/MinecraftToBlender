//go:build windows

package main

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"strings"
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

func TestPreviewMatchesOnlySelectedWorld(t *testing.T) {
	previous := app.selectedWorld
	defer func(){ app.selectedWorld = previous }()
	source := filepath.Join(t.TempDir(), "MinecraftSaves", "World A")
	app.selectedWorld = &localWorld{path: source}
	if !previewWorldMatches(source) || !previewWorldMatches(strings.ToUpper(source)) {
		t.Fatal("preview for the same world must remain selectable on Windows")
	}
	if previewWorldMatches(filepath.Join(filepath.Dir(source), "World B")) {
		t.Fatal("preview from a different world must not change coordinates")
	}
	app.selectedWorld = nil
	if previewWorldMatches(source) {
		t.Fatal("preview should not edit coordinates when no world is selected")
	}
}
