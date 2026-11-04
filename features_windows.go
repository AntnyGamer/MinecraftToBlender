//go:build windows

package main

import (
	"context"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"syscall"
	"time"
	"unsafe"
)

func resumeLabel() string {
	if app.resumeEnabled {
		return "Safe resume: On"
	}
	return "Safe resume: Off"
}

func toggleEntity(id int) {
	var enabled *bool
	var title string
	switch id {
	case idEntityFrames:
		enabled, title = &app.entityFrames, "Item frames"
	case idEntityPaintings:
		enabled, title = &app.entityPaintings, "Paintings"
	case idEntityStands:
		enabled, title = &app.entityStands, "Armor stands"
	case idEntityDisplays:
		enabled, title = &app.entityDisplays, "Displays"
	default:
		return
	}
	*enabled = !*enabled
	mode := "Off"
	if *enabled {
		mode = "On"
	}
	setText(app.ctrls[id], title+": "+mode)
	refreshButtons()
}

var pFreeDisk = kernel32.NewProc("GetDiskFreeSpaceExW")
var pMemoryStatus = kernel32.NewProc("GlobalMemoryStatusEx")

type memoryStatus struct {
	Size         uint32
	MemoryLoad   uint32
	TotalPhys    uint64
	AvailPhys    uint64
	TotalPage    uint64
	AvailPage    uint64
	TotalVirtual uint64
	AvailVirtual uint64
	AvailExtended uint64
}

func availableDisk(path string) (uint64, error) {
	abs, err := filepath.Abs(path)
	if err != nil {
		return 0, err
	}
	volume := filepath.VolumeName(abs)
	if volume == "" {
		return 0, fmt.Errorf("volume unavailable for %s", abs)
	}
	var free uint64
	ret, _, err := pFreeDisk.Call(uintptr(unsafe.Pointer(syscall.StringToUTF16Ptr(volume+"\\"))), uintptr(unsafe.Pointer(&free)), 0, 0)
	if ret == 0 {
		return 0, err
	}
	return free, nil
}

func physicalRAM() uint64 {
	m := memoryStatus{Size: uint32(unsafe.Sizeof(memoryStatus{}))}
	ok, _, _ := pMemoryStatus.Call(uintptr(unsafe.Pointer(&m)))
	if ok == 0 {
		return 0
	}
	return m.TotalPhys
}

func readiness(world localWorld, workspace, blender, dim string, size, x, z int, alsoImport bool) (string, []string) {
	var info, warnings []string
	if !validWorldDir(world.path, world.edition) {
		warnings = append(warnings, "The selected save is unavailable.")
	} else {
		info = append(info, "World: "+world.name+" ("+string(world.edition)+")")
	}
	info = append(info, fmt.Sprintf("Dimension: %s; region %dx%d, center (%d,%d)", dimensionLabel(dim), size, size, x, z))
	if world.edition == javaEdition {
		dir := world.path
		if dim == "the_nether" { dir = filepath.Join(dir, "DIM-1") }
		if dim == "the_end" { dir = filepath.Join(dir, "DIM1") }
		regionDir := filepath.Join(dir, "region")
		if _, err := os.Stat(regionDir); err != nil {
			warnings = append(warnings, "Selected Java dimension has no region folder yet.")
		}
	} else if dim != "overworld" {
		info = append(info, "MiEx will check Bedrock dimension records during export.")
	}
	if !worldCenterOutsideRegion(x, z, size, world.x, world.z) && world.hasCenter && dim == "overworld" {
		info = append(info, "The selection contains the recorded player/spawn center.")
	}
	if _, err := exec.LookPath("java.exe"); err != nil {
		warnings = append(warnings, "Java is not available on PATH.")
	} else {
		ctx, cancel := context.WithTimeout(context.Background(), 4*time.Second)
		cmd := exec.CommandContext(ctx, "java.exe", "-version")
		data, err := cmd.CombinedOutput()
		cancel()
		if err != nil {
			warnings = append(warnings, "Java version check failed: "+err.Error())
		} else {
			first := strings.TrimSpace(strings.SplitN(string(data), "\n", 2)[0])
			info = append(info, "Java: "+first)
			if major := javaMajorVersion(first); major != 0 && major < 21 {
				warnings = append(warnings, fmt.Sprintf("Java %d is too old; MiEx requires Java 21 or newer.",major))
			}
		}
	}
	if alsoImport {
		if s, err := os.Stat(blender); err != nil || s.IsDir() {
			warnings = append(warnings, "Blender executable cannot be found.")
		} else {
			ctx, cancel := context.WithTimeout(context.Background(), 6*time.Second)
			data, err := exec.CommandContext(ctx, blender, "--version").CombinedOutput()
			cancel()
			if err != nil {
				warnings = append(warnings, "Blender could not report its version: "+err.Error())
			} else {
				info = append(info, "Blender: "+strings.TrimSpace(strings.SplitN(string(data),"\n",2)[0]))
			}
		}
	}
	if ram := physicalRAM(); ram != 0 {
		info = append(info, fmt.Sprintf("Physical memory: %.1f GiB", float64(ram)/(1<<30)))
		if ram < 8<<30 {
			warnings = append(warnings, "Under 8 GiB of physical RAM: large exports may run out of memory.")
		}
	}
	if disk, err := availableDisk(workspace); err == nil {
		info = append(info, fmt.Sprintf("Workspace free space: %.1f GiB", float64(disk)/(1<<30)))
		if disk < 5<<30 {
			warnings = append(warnings, "Under 5 GiB available in the workspace.")
		}
	} else if _, err := os.Stat(workspace); err == nil {
		warnings = append(warnings, "Couldn't determine available workspace disk space.")
	}
	return strings.Join(info, "\n"), warnings
}

func javaMajorVersion(line string) int {
	quoted := strings.Split(line, "\"")
	if len(quoted) < 2 {return 0}
	parts := strings.Split(quoted[1], ".")
	major, err := strconv.Atoi(parts[0])
	if err != nil {return 0}
	if major == 1 && len(parts) > 1 {
		legacy, err := strconv.Atoi(parts[1])
		if err == nil {return legacy}
	}
	return major
}

func showPreflight() {
	if app.selectedWorld == nil {
		alert("Choose a world", "Select a Minecraft world before checking readiness.", mbWarn)
		return
	}
	world := *app.selectedWorld
	size, errSize := strconv.Atoi(strings.TrimSpace(getText(idSize)))
	x, errX := strconv.Atoi(strings.TrimSpace(getText(idX)))
	z, errZ := strconv.Atoi(strings.TrimSpace(getText(idZ)))
	if errSize != nil || errX != nil || errZ != nil || size < 16 || size > 8192 || size%16 != 0 {
		alert("Invalid region", "Enter a valid block area and center coordinates in Export world first.", mbWarn)
		return
	}
	info, warnings := readiness(world, getText(idWorkspace), getText(idBlender), app.dimension, size, x, z, false)
	text := info
	if len(warnings) > 0 {
		text += "\n\nWARNINGS:\n- "+strings.Join(warnings, "\n- ")
	} else {
		text += "\n\nNo obvious configuration issues detected. This does not guarantee a successful export."
	}
	alert("Pre-export readiness", text, 0)
}

func startPreview() {
	if app.busy { return }
	if app.selectedWorld == nil {
		alert("Choose a world", "Select a Minecraft world before generating a preview.", mbWarn)
		return
	}
	size, es := intField(idSize, 16, 8192)
	x, ex := intField(idX, -30000000, 30000000)
	z, ez := intField(idZ, -30000000, 30000000)
	if es != nil || ex != nil || ez != nil || size%16 != 0 {
		alert("Invalid preview area", "Choose a multiple-of-16 area and valid center X/Z.", mbWarn)
		return
	}
	world := *app.selectedWorld
	workspace := strings.TrimSpace(getText(idWorkspace))
	if workspace == "" || pathsOverlap(world.path, toolsDir(workspace)) {
		alert("Invalid workspace", "Choose a workspace outside the Minecraft world folder.", mbWarn)
		return
	}
	ctx, cancel := context.WithCancel(context.Background())
	app.cancel = cancel
	resetLog()
	setBusy(true)
	state("Sampling world chunks for region preview...")
	go func() {
		app.doneCh <- runPreview(ctx, world, workspace, app.dimension, size, x, z)
	}()
}
