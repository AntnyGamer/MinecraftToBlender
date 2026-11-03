//go:build windows

package main

import (
	"context"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"testing"
	"time"
)

func TestRunProcessPreservesLargeLogs(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 45*time.Second)
	defer cancel()

	logFile := filepath.Join(t.TempDir(), "process.log")
	code := "$line = 'x' * 256; 1..2048 | ForEach-Object { [Console]::Out.WriteLine('LINE_' + $_ + ':' + $line) }"
	if err := runProcess(ctx, "powershell.exe", []string{"-NoProfile", "-NonInteractive", "-Command", code}, logFile); err != nil {
		t.Fatal(err)
	}
	data, err := os.ReadFile(logFile)
	if err != nil {
		t.Fatal(err)
	}
	lines := strings.Split(strings.TrimSuffix(string(data), "\n"), "\n")
	if len(lines) != 2048 {
		t.Fatalf("got %d log lines, want 2048", len(lines))
	}
	for i, line := range lines {
		want := "LINE_" + strconv.Itoa(i+1) + ":" + strings.Repeat("x", 256)
		if line != want {
			t.Fatalf("incorrect log line %d: %q", i+1, line)
		}
	}
}
