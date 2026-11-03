//go:build windows

package main

import (
	"reflect"
	"testing"
)

func TestBlenderProjectCommandNoConsole(t *testing.T) {
	blender := `C:\Program Files\Blender Foundation\Blender 5.2\blender.exe`
	project := `C:\Minecraft Exports\My World.blend`
	cmd := blenderProjectCommand(blender, project)
	if cmd.Path != blender {
		t.Fatalf("Blender executable changed: %q", cmd.Path)
	}
	if want := []string{blender, project}; !reflect.DeepEqual(cmd.Args, want) {
		t.Fatalf("Blender launch arguments: got %q, want %q", cmd.Args, want)
	}
	if cmd.SysProcAttr == nil || cmd.SysProcAttr.CreationFlags&createNoWindow == 0 {
		t.Fatal("Blender GUI launch must suppress the console window")
	}
	if cmd.SysProcAttr.HideWindow {
		t.Fatal("HideWindow would risk hiding Blender's main GUI")
	}
}
