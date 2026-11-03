//go:build windows

package main

import (
	"os"
	"testing"
)

func TestAutoOpenBlenderPreference(t *testing.T) {
	t.Setenv("LOCALAPPDATA", t.TempDir())
	if !loadAutoOpenBlender() {
		t.Fatal("auto-open should default to enabled")
	}
	for _, value := range []bool{false, true, false} {
		if err := saveAutoOpenBlender(value); err != nil {
			t.Fatal(err)
		}
		if got := loadAutoOpenBlender(); got != value {
			t.Fatalf("preference after save: got %t, want %t", got, value)
		}
	}
	if err := os.WriteFile(autoOpenPreferencePath(), []byte("invalid JSON"), 0644); err != nil {
		t.Fatal(err)
	}
	if !loadAutoOpenBlender() {
		t.Fatal("invalid preferences should fall back to enabled")
	}
}
