package main

import (
    "strings"
    "testing"
)

func TestDimensionCycle(t *testing.T) {
	if nextDimension("overworld") != "the_nether" || nextDimension("the_nether") != "the_end" || nextDimension("the_end") != "overworld" {
		t.Fatal("dimension cycle is invalid")
	}
}

func TestEntitySelection(t *testing.T) {
	all := exportOptions{Frames: true, Paintings: true, Stands: true, Displays: true}
	if len(strings.Split(all.EntityList(), ",")) != 6 {
		t.Fatalf("expected all six entities, got %q", all.EntityList())
	}
	if (exportOptions{}).EntityList() != "none" {
		t.Fatal("zero-entity selection should use explicit none sentinel")
	}
	if (exportOptions{Paintings: true}).EntityList() != "minecraft:painting" {
		t.Fatal("paintings selection failed")
	}
}
