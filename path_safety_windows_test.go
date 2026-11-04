//go:build windows

package main

import (
	"os"
	"path/filepath"
	"testing"
)

func TestPathsOverlapResolvesSymlinkedWorkspace(t *testing.T) {
	root := t.TempDir()
	world := filepath.Join(root, "save")
	if err := os.MkdirAll(world, 0700); err != nil {
		t.Fatal(err)
	}
	alias := filepath.Join(root, "saveAlias")
	if err := os.Symlink(world, alias); err != nil {
		// Windows without Developer Mode or symlink privileges can still use
		// junctions. Keep the test portable across GitHub Windows runners.
		t.Skipf("creating a directory symlink requires Windows privileges: %v", err)
	}
	if !pathsOverlap(world, filepath.Join(alias, "AppTools")) {
		t.Fatal("workspace inside a symlink alias of the Minecraft save was accepted")
	}
	if !pathsOverlap(filepath.Join(alias, "nether"), filepath.Join(world, "nether", "AppTools")) {
		t.Fatal("nested source/world alias overlap was not detected")
	}
	if pathsOverlap(world, filepath.Join(root, "separateWorkspace", "AppTools")) {
		t.Fatal("separate workspace was incorrectly marked as overlapping")
	}
}

func TestPathsOverlapResolvesNotYetCreatedChildren(t *testing.T) {
	root := t.TempDir()
	world := filepath.Join(root, "world")
	if err := os.MkdirAll(world, 0700); err != nil {
		t.Fatal(err)
	}
	if !pathsOverlap(world, filepath.Join(world, "new-workspace", "AppTools")) {
		t.Fatal("nested not-yet-created workspace was accepted")
	}
	if pathsOverlap(world, filepath.Join(root, "another-workspace", "AppTools")) {
		t.Fatal("disjoint not-yet-created workspace was rejected")
	}
}
