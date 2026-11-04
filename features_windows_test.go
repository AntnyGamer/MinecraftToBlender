//go:build windows

package main

import (
	"context"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestJavaMajorVersion(t *testing.T) {
	cases:=map[string]int {
		`openjdk version "21.0.5" 2024-10-15`:21,
		`java version "1.8.0_421"`:8,
		`openjdk version "25" 2025-09-16`:25,
		`unrecognized Java output`:0,
	}
	for text,want:=range cases {
		if got:=javaMajorVersion(text);got!=want {
			t.Fatalf("%s: got Java %d, want %d",text,got,want)
		}
	}
}

func TestReadinessWarnsWhenWorkspaceIsAFile(t *testing.T) {
	workspace := filepath.Join(t.TempDir(), "not-a-folder")
	if err := os.WriteFile(workspace, []byte("file"), 0600); err != nil {
		t.Fatal(err)
	}
	world := localWorld{path: filepath.Join(t.TempDir(), "world"), edition: bedrockEdition}
	_, warnings := readiness(context.Background(), world, workspace, "", "overworld", 256, 0, 0, false, false)
	joined := strings.Join(warnings, "\n")
	if !strings.Contains(joined, "workspace is a file") {
		t.Fatalf("expected workspace file warning, got %q", joined)
	}
}
