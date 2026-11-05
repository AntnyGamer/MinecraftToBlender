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
	defer func() { app.selectedWorld = previous }()
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

func TestPreviewRejectsSaveWorkspaceOverlapBeforeWriting(t *testing.T) {
	for _, layout := range []string{"inside-save", "nested-inside-save", "save-inside-tools"} {
		t.Run(layout, func(t *testing.T) {
			root := t.TempDir()
			world := filepath.Join(root, "save")
			workspace := world
			if layout == "nested-inside-save" {
				workspace = filepath.Join(world, "new-workspace")
			} else if layout == "save-inside-tools" {
				workspace = root
				world = filepath.Join(toolsDir(workspace), "save")
			}
			writeFixtureWorld(t, world, bedrockEdition, "Untouched save", 1750000000)
			before, err := digestDirectory(context.Background(), root)
			if err != nil {
				t.Fatal(err)
			}
			result := runPreview(context.Background(), localWorld{path: world, edition: bedrockEdition}, workspace, "overworld", false, 16, 0, 0)
			if result.err == nil || !strings.Contains(result.err.Error(), "workspace conflicts") {
				t.Fatalf("unsafe preview workspace accepted: %v", result.err)
			}
			after, err := digestDirectory(context.Background(), root)
			if err != nil || after != before {
				t.Fatalf("rejected preview changed the Minecraft save/workspace: %v", err)
			}
		})
	}
}
