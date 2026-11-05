//go:build windows

package main

import (
	"context"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func TestSystemHelpersIgnoreUntrustedSearchPaths(t *testing.T) {
	names := []string{"powershell.exe", "taskkill.exe", "explorer.exe"}
	want := make(map[string]string)
	for _, name := range names {
		path, err := trustedSystemExecutable(name)
		if err != nil {
			t.Fatal(err)
		}
		if _, err := os.Stat(path); err != nil {
			t.Fatalf("Windows helper unavailable: %s: %v", path, err)
		}
		want[name] = path
	}
	untrusted := t.TempDir()
	systemRoot, windir := os.Getenv("SystemRoot"), os.Getenv("WINDIR")
	for _, name := range names {
		if err := os.WriteFile(filepath.Join(untrusted, name), []byte("not an executable"), 0600); err != nil {
			t.Fatal(err)
		}
	}
	t.Setenv("PATH", untrusted)
	t.Setenv("SystemRoot", untrusted)
	t.Setenv("WINDIR", untrusted)
	for _, name := range names {
		got, err := trustedSystemExecutable(strings.ToUpper(name))
		if err != nil || got != want[name] {
			t.Fatalf("untrusted environment changed %s: %q, %v", name, got, err)
		}
	}
	// Exercise the real export process launcher, not just path construction.
	// PowerShell itself requires the real SystemRoot to initialize .NET.
	t.Setenv("SystemRoot", systemRoot)
	t.Setenv("WINDIR", windir)
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	log := filepath.Join(t.TempDir(), "trusted.log")
	if err := runProcess(ctx, "powershell.exe", []string{"-NoProfile", "-NonInteractive", "-Command", "[Console]::WriteLine('trusted-helper')"}, log); err != nil {
		t.Fatal(err)
	}
	data, err := os.ReadFile(log)
	if err != nil || strings.TrimSpace(string(data)) != "trusted-helper" {
		t.Fatalf("real PowerShell launch failed: %q, %v", data, err)
	}
}

func TestSystemHelperResolutionPreservesUserExecutables(t *testing.T) {
	for _, name := range []string{`C:\My Blender\blender.exe`, "java.exe", `D:\Tools\powershell.exe`} {
		got, err := trustedSystemExecutable(name)
		if err != nil || got != name {
			t.Fatalf("user executable changed: %q => %q, %v", name, got, err)
		}
	}
}
