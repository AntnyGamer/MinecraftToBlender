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

func physicalRAM() (uint64, uint64) {
	m := memoryStatus{Size: uint32(unsafe.Sizeof(memoryStatus{}))}
	ok, _, _ := pMemoryStatus.Call(uintptr(unsafe.Pointer(&m)))
	if ok == 0 {
		return 0, 0
	}
	return m.TotalPhys, m.AvailPhys
}

// Readiness checks must never briefly open console windows in the GUI.
func hiddenCheckCommand(ctx context.Context, name string, args ...string) *exec.Cmd {
	cmd := exec.CommandContext(ctx, name, args...)
	cmd.SysProcAttr = &syscall.SysProcAttr{HideWindow: true, CreationFlags: createNoWindow}
	return cmd
}

func readiness(ctx context.Context, world localWorld, workspace, blender, dim string, size, x, z int, alsoImport, deep bool) (string, []string) {
	var info, warnings []string
	if !validWorldDir(world.path, world.edition) {
		warnings = append(warnings, "The selected save is unavailable.")
	} else {
		info = append(info, "World: "+world.name+" ("+string(world.edition)+")")
	}
	info = append(info, fmt.Sprintf("Dimension: %s; region %dx%d, center (%d,%d)", dimensionLabel(dim), size, size, x, z))
	if world.edition == javaEdition {
		if deep {
			hasChunks, err := javaRegionHasSavedChunksContext(ctx, world.path, dim, size, x, z)
			if err != nil {
				warnings = append(warnings, "Cannot inspect saved Java chunks: "+err.Error())
			} else if !hasChunks {
				warnings = append(warnings, "No saved Java chunks were found in this selected region and dimension.")
			} else {
				info = append(info, "Saved Java chunks found inside the selected region.")
			}
		} else {
			// The automatic pre-export check runs on the GUI thread. Do not
			// scan potentially thousands of Anvil region files there: the
			// detailed Check readiness action does that in a cancellable worker.
			regionDir, err := javaDimensionRegionPath(world.path, dim)
			if err != nil {
				warnings = append(warnings, err.Error())
			} else if st, err := os.Stat(regionDir); err != nil || !st.IsDir() {
				warnings = append(warnings, "Selected Java dimension has no saved region folder.")
			} else {
				info = append(info, "Java region folder found; Check readiness can inspect saved chunks.")
			}
		}
	} else {
		info = append(info, "Bedrock chunk contents will be sampled by MiEx during preview/export.")
	}
	if !worldCenterOutsideRegion(x, z, size, world.x, world.z) && world.hasCenter && dim == "overworld" {
		info = append(info, "The selection contains the recorded player/spawn center.")
	}
	if _, err := exec.LookPath("java.exe"); err != nil {
		warnings = append(warnings, "Java is not available on PATH.")
	} else if deep {
		checkCtx, cancel := context.WithTimeout(ctx, 4*time.Second)
		data, err := hiddenCheckCommand(checkCtx, "java.exe", "-version").CombinedOutput()
		cancel()
		if err != nil {
			warnings = append(warnings, "Java version check failed: "+err.Error())
		} else {
			first := strings.TrimSpace(strings.SplitN(string(data), "\n", 2)[0])
			info = append(info, "Java: "+first)
			if major := javaMajorVersion(first); major != 0 && major < 21 {
				warnings = append(warnings, fmt.Sprintf("Java %d is too old; MiEx requires Java 21 or newer.", major))
			}
		}
	} else {
		info = append(info, "Java found on PATH (version check available under Check readiness).")
	}
	if alsoImport {
		if s, err := os.Stat(blender); err != nil || s.IsDir() {
			warnings = append(warnings, "Blender executable cannot be found.")
		} else if deep {
			checkCtx, cancel := context.WithTimeout(ctx, 6*time.Second)
			data, err := hiddenCheckCommand(checkCtx, blender, "--version").CombinedOutput()
			cancel()
			if err != nil {
				warnings = append(warnings, "Blender could not report its version: "+err.Error())
			} else {
				info = append(info, "Blender: "+strings.TrimSpace(strings.SplitN(string(data),"\n",2)[0]))
			}
		} else {
			info = append(info, "Blender executable found (version check available under Check readiness).")
		}
	}
	if ram, available := physicalRAM(); ram != 0 {
		info = append(info, fmt.Sprintf("Physical memory: %.1f GiB total, %.1f GiB available", float64(ram)/(1<<30), float64(available)/(1<<30)))
		if ram < 8<<30 {
			warnings = append(warnings, "Under 8 GiB of physical RAM: large exports may run out of memory.")
		}
		if available < 2<<30 {
			warnings = append(warnings, "Less than 2 GiB of RAM currently available. Close memory-heavy programs before a large export.")
		}
	}
	if strings.TrimSpace(workspace) == "" {
		warnings = append(warnings, "Choose a workspace folder before exporting.")
	} else {
		if st, err := os.Stat(workspace); err == nil {
			if !st.IsDir() {
				warnings = append(warnings, "The selected workspace is a file, not a folder.")
			}
		} else if !os.IsNotExist(err) {
			warnings = append(warnings, "Cannot access the selected workspace: "+err.Error())
		}
		if pathsOverlap(world.path, toolsDir(workspace)) {
			warnings = append(warnings, "Workspace and Minecraft save folders overlap. Move the workspace outside the world.")
		}
		if disk, err := availableDisk(workspace); err == nil {
			info = append(info, fmt.Sprintf("Workspace free space: %.1f GiB", float64(disk)/(1<<30)))
			if disk < 5<<30 {
				warnings = append(warnings, "Under 5 GiB available in the workspace.")
			}
		} else {
			warnings = append(warnings, "Couldn't determine available workspace disk space.")
		}
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
	if app.busy {
		return
	}
	if app.selectedWorld == nil {
		alert("Choose a world", "Select a Minecraft world before checking readiness.", mbWarn)
		return
	}
	size, es := intField(idSize, 16, 8192)
	x, ex := intField(idX, -30000000, 30000000)
	z, ez := intField(idZ, -30000000, 30000000)
	if es != nil || ex != nil || ez != nil || size%16 != 0 {
		alert("Invalid region", "Enter a valid block area and center coordinates in Export world first.", mbWarn)
		return
	}
	minY, eMin := intField(idMinY, -256, 2048)
	maxY, eMax := intField(idMaxY, -256, 2048)
	if eMin != nil || eMax != nil || minY > maxY {
		alert("Invalid height range", "Minimum Y must not exceed maximum Y; use -256 through 2048.", mbWarn)
		return
	}
	world := *app.selectedWorld
	workspace := strings.TrimSpace(getText(idWorkspace))
	blender := strings.TrimSpace(getText(idBlender))
	dimension := app.dimension
	ctx, cancel := context.WithCancel(context.Background())
	app.cancel = cancel
	resetLog()
	setBusy(true)
	state("Checking Minecraft world, Java, Blender and system resources...")
	go func() {
		info, warnings := readiness(ctx, world, workspace, blender, dimension, size, x, z, blender != "", true)
		if err := ctx.Err(); err != nil {
			app.doneCh <- result{what: "Pre-export readiness", err: err}
			return
		}
		message := info
		if len(warnings) != 0 {
			message += "\n\nWARNINGS:\n- " + strings.Join(warnings, "\n- ")
		} else {
			message += "\n\nNo obvious configuration issues detected. This does not guarantee a successful export."
		}
		app.doneCh <- result{what: "Pre-export readiness", output: message}
	}()
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
	dimension := app.dimension
	useWorldPacks := app.useWorldPacks
	ctx, cancel := context.WithCancel(context.Background())
	app.cancel = cancel
	resetLog()
	setBusy(true)
	state("Sampling world chunks for region preview...")
	go func() {
		app.doneCh <- runPreview(ctx, world, workspace, dimension, useWorldPacks, size, x, z)
	}()
}
