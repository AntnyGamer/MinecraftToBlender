//go:build windows

package main

import (
	"fmt"
	"strings"
	"testing"
)

func TestStandardEditLogAppendPreservesText(t *testing.T) {
	// Exercise the actual Windows standard EDIT control used when RichEdit
	// is unavailable. No text is discarded during repeated append operations.
	h, _, err := pCreateWindow.Call(0, ptr("EDIT"), ptr(""),
		uintptr(wsOverlappedWindow|esMultiline|esReadOnly|wsVScroll),
		0, 0, 320, 160, 0, 0, 0, 0)
	if h == 0 {
		t.Fatalf("cannot create Windows standard EDIT: %v", err)
	}
	defer pDestroyWindow.Call(h)

	oldControl := app.ctrls[idLog]
	oldLines := app.logLines
	oldShown := app.logShown
	oldFollow := app.followLog
	oldRich := ui.rich
	t.Cleanup(func() {
		app.ctrls[idLog] = oldControl
		app.logLines = oldLines
		app.logShown = oldShown
		app.followLog = oldFollow
		ui.rich = oldRich
	})

	app.ctrls[idLog] = h
	app.logLines = nil
	app.logShown = 0
	app.followLog = true
	ui.rich = false
	var want strings.Builder
	for batch := 0; batch < 15; batch++ {
		for i := 0; i < 37; i++ {
			line := fmt.Sprintf("conversion %02d %03d: terrain and textures intact", batch, i)
			app.logLines = append(app.logLines, line)
			want.WriteString(line)
			want.WriteString("\r\n")
		}
		updateLog()
		if got := getText(idLog); got != want.String() {
			t.Fatalf("batch %d changed log contents: got %d bytes, want %d bytes", batch, len(got), want.Len())
		}
	}
}
