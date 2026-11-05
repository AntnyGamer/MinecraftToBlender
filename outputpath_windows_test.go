//go:build windows

package main

import (
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"testing"
)

func TestBlenderOutputWorldName(t *testing.T) {
	name := safeExportName("Night Blades Survival")
	if name != "Night_Blades_Survival" {
		t.Fatalf("sanitized world name = %q", name)
	}
	dir := t.TempDir()
	src := filepath.Join(dir, name+".usd")
	for _, want := range []string{name + ".blend", name + "_2.blend", name + "_3.blend"} {
		got, err := blenderOutputPath(src)
		if err != nil || got != filepath.Join(dir, want) {
			t.Fatalf("next output = %q, %v; want %q", got, err, want)
		}
		if err := os.WriteFile(got, []byte("existing project"), 0600); err != nil {
			t.Fatal(err)
		}
	}
}

func TestBlenderOutputPathLimit(t *testing.T) {
	dir := t.TempDir()
	for i := 1; i <= 100; i++ {
		path := filepath.Join(dir, "World.blend")
		if i > 1 {
			path = filepath.Join(dir, "World_"+strconv.Itoa(i)+".blend")
		}
		if i == 100 {
			got, err := blenderOutputPath(filepath.Join(dir, "World.usd"))
			if err != nil || got != path {
				t.Fatalf("last available name = %q, %v; want %q", got, err, path)
			}
		}
		if err := os.WriteFile(path, nil, 0600); err != nil {
			t.Fatal(err)
		}
	}
	_, err := blenderOutputPath(filepath.Join(dir, "World.usd"))
	if err == nil || !strings.Contains(err.Error(), "100") {
		t.Fatalf("expected limit error; got %v", err)
	}
}

func TestExistingBlenderProjectGetsNewOutput(t *testing.T) {
	dir := t.TempDir()
	source := filepath.Join(dir, "MyWorld.blend")
	if err := os.WriteFile(source, []byte("original project"), 0600); err != nil {
		t.Fatal(err)
	}
	target, err := blenderOutputPath(source)
	if err != nil {
		t.Fatal(err)
	}
	if want := filepath.Join(dir, "MyWorld_2.blend"); target != want {
		t.Fatalf("existing Blender project target = %q, want %q", target, want)
	}
	if err := os.WriteFile(target, []byte("optimized project"), 0600); err != nil {
		t.Fatal(err)
	}
	other, err := blenderOutputPath(source)
	if err != nil {
		t.Fatal(err)
	}
	if want := filepath.Join(dir, "MyWorld_3.blend"); other != want {
		t.Fatalf("second optimization target = %q, want %q", other, want)
	}
	data, err := os.ReadFile(source)
	if err != nil || string(data) != "original project" {
		t.Fatalf("optimizing existing Blender project altered original file: %q, %v", data, err)
	}
}
