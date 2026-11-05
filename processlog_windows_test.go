//go:build windows

package main

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"testing"
	"time"
)

func TestCancelledProcessPreservesExistingLog(t *testing.T) {
	logFile := filepath.Join(t.TempDir(), "previous.log")
	if err := os.WriteFile(logFile, []byte("previous diagnostics"), 0600); err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	err := runProcess(ctx, "nonexistent.exe", nil, logFile)
	if !errors.Is(err, context.Canceled) {
		t.Fatalf("cancelled process returned %v", err)
	}
	data, err := os.ReadFile(logFile)
	if err != nil || string(data) != "previous diagnostics" {
		t.Fatalf("cancelled operation replaced previous diagnostics: %q, %v", data, err)
	}
}

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
		// Preserve the child's original CRLF on Windows when streaming logs.
		line = strings.TrimSuffix(line, "\r")
		if line != want {
			t.Fatalf("incorrect log line %d: %q", i+1, line)
		}
	}
}

func TestRunProcessPreservesLinesOverEightMegabytes(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 60*time.Second)
	defer cancel()

	path := filepath.Join(t.TempDir(), "huge.log")
	const size = 9 * 1024 * 1024
	code := "$line = 'Q' * " + strconv.Itoa(size) + "; [Console]::Out.WriteLine($line)"
	if err := runProcess(ctx, "powershell.exe", []string{"-NoProfile", "-NonInteractive", "-Command", code}, path); err != nil {
		t.Fatal(err)
	}
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	if len(data) < size || data[0] != 'Q' || data[size-1] != 'Q' {
		t.Fatalf("large output was truncated: saved %d bytes, expected at least %d", len(data), size)
	}
}
