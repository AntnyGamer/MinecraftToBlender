//go:build windows

package main

import "testing"

func TestPickerVisibleRange(t *testing.T) {
	tests := []struct {
		name                       string
		scroll, height, total       int
		wantFirst, wantLast          int
	}{
		{"empty", 0, 300, 0, 0, 0},
		{"first page", 0, 300, 500, 0, 5},
		{"scrolled", 910, 300, 500, 9, 15},
		{"end", 910, 300, 12, 9, 12},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			first, last := pickerVisibleRange(tc.scroll, tc.height, tc.total)
			if first != tc.wantFirst || last != tc.wantLast {
				t.Fatalf("range = [%d, %d), want [%d, %d)", first, last, tc.wantFirst, tc.wantLast)
			}
		})
	}
}

func TestPickerImagesLoadOnlyWhenVisible(t *testing.T) {
	original := picker
	picker = pickerState{
		worlds: []localWorld{
			{icon: "C:\\nonexistent_MiEx_icon_0.png"},
			{icon: "C:\\nonexistent_MiEx_icon_1.png"},
			{icon: "C:\\nonexistent_MiEx_icon_2.png"},
		},
	}
	t.Cleanup(func() {
		pickerReleaseImages()
		if picker.gdipToken != 0 {
			pGdiplusShutdown.Call(picker.gdipToken)
		}
		picker = original
	})
	pickerLoadImages()
	if picker.gdipToken == 0 {
		t.Skip("GDI+ unavailable on this Windows runner")
	}
	if len(picker.images) != 3 || len(picker.imageAttempted) != 3 {
		t.Fatalf("expected deferred icon slots for all worlds")
	}
	for i := range picker.imageAttempted {
		if picker.imageAttempted[i] || picker.images[i] != 0 {
			t.Fatalf("icon %d was decoded before it was visible", i)
		}
	}
	pickerLoadVisibleImages(1, 2)
	if picker.imageAttempted[0] || !picker.imageAttempted[1] || picker.imageAttempted[2] {
		t.Fatal("loading a visible row loaded off-screen thumbnails")
	}
	pickerLoadVisibleImages(1, 2)
	if !picker.imageAttempted[1] || picker.images[1] != 0 {
		t.Fatal("failed image lookup was not cached")
	}
	pickerLoadVisibleImages(0, 3)
	for i, attempted := range picker.imageAttempted {
		if !attempted {
			t.Fatalf("icon %d was not loaded after coming into view", i)
		}
	}
	pickerReleaseImages()
	if picker.images != nil || picker.imageAttempted != nil {
		t.Fatal("thumbnail cache was not released on refresh")
	}
}
