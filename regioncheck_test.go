package main

import "testing"

func TestWorldCenterOutsideRegion(t *testing.T) {
	tests := []struct {
		cx, cz, size, x, z int
		outside            bool
	}{
		{0, 0, 1024, 0, 0, false},
		{0, 0, 1024, -512, 511, false},
		{0, 0, 1024, -513, 0, true},
		{0, 0, 1024, 512, 0, true},
		{0, 0, 1024, 0, 512, true},
		{2000, -2000, 16, 1992, -1993, false},
		{2000, -2000, 16, 1991, -1993, true},
	}
	for _, tt := range tests {
		if got := worldCenterOutsideRegion(tt.cx, tt.cz, tt.size, tt.x, tt.z); got != tt.outside {
			t.Errorf("region centered (%d,%d) size %d saved (%d,%d): got %v, want %v", tt.cx, tt.cz, tt.size, tt.x, tt.z, got, tt.outside)
		}
	}
}
