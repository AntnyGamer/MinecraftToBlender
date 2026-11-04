//go:build windows

package main

import (
	"strings"
	"testing"
)

func TestGuiLogBoundsLargeMessagesBeforeQueuing(t *testing.T) {
	original := app.logCh
	app.logCh = make(chan string, 3)
	t.Cleanup(func() { app.logCh = original })
	for _, line := range []string{"small", strings.Repeat("x", 4000), strings.Repeat("z", 1024*1024)} {
		guiLog(line)
		got := <-app.logCh
		want := line
		if len(line) > 4000 {
			want = line[:4000] + "..."
		}
		if got != want {
			t.Fatalf("UI queue changed visible content for input %d bytes", len(line))
		}
		if len(got) > 4003 {
			t.Fatalf("UI retained an oversized diagnostic of %d bytes", len(got))
		}
	}
	guiLog(strings.Repeat(" ", 1024*1024))
	select {
	case message := <-app.logCh:
		t.Fatalf("oversized whitespace-only log should remain invisible: %q", message)
	default:
	}
}
