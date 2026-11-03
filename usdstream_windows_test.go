//go:build windows

package main

import (
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"testing"
)

func TestUSDValidationStreamsManyChunkEntries(t *testing.T) {
	dir := t.TempDir()
	mainUSD := filepath.Join(dir, "Large_World.usd")
	chunks := filepath.Join(dir, "Large_World_chunks")
	if err := os.WriteFile(mainUSD, []byte("#usda 1.0\n"), 0644); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(dir, "Large_World_materials.json"), []byte("{}"), 0644); err != nil {
		t.Fatal(err)
	}
	if err := os.Mkdir(chunks, 0755); err != nil {
		t.Fatal(err)
	}
	for i := 0; i < 350; i++ {
		p := filepath.Join(chunks, "empty_"+strconv.Itoa(i)+".usd")
		if err := os.WriteFile(p, nil, 0644); err != nil {
			t.Fatal(err)
		}
	}
	// A nested USD file does not count as an immediate chunk layer.
	nested := filepath.Join(chunks, "nested")
	if err := os.Mkdir(nested, 0755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(nested, "hidden.usd"), []byte("data"), 0644); err != nil {
		t.Fatal(err)
	}
	if err := usdFiles(mainUSD); err == nil || !strings.Contains(err.Error(), "no non-empty USD") {
		t.Fatalf("expected missing chunk error, got %v", err)
	}
	// The valid file can be encountered after several bounded batches.
	valid := filepath.Join(chunks, "last_chunk.USD")
	if err := os.WriteFile(valid, []byte("valid layer"), 0644); err != nil {
		t.Fatal(err)
	}
	if err := usdFiles(mainUSD); err != nil {
		t.Fatalf("expected valid exported chunk, got %v", err)
	}
	if err := os.WriteFile(filepath.Join(dir, "Large_World_materials.json"), []byte("{"), 0644); err != nil {
		t.Fatal(err)
	}
	if err := usdFiles(mainUSD); err == nil || !strings.Contains(err.Error(), "not valid") {
		t.Fatalf("streaming must retain materials validation, got %v", err)
	}
}
