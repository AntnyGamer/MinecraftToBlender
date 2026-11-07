//go:build windows

package main

// A world-select screen with Minecraft-inspired colors and native Windows controls.
// Thumbnails are read from the worlds themselves; no game textures are bundled.
import (
	"fmt"
	"strings"
	"syscall"
	"unsafe"
)

var (
	gdiplus             = syscall.NewLazyDLL("gdiplus.dll")
	pGdiplusStartup     = gdiplus.NewProc("GdiplusStartup")
	pGdiplusShutdown    = gdiplus.NewProc("GdiplusShutdown")
	pGdipLoadImage      = gdiplus.NewProc("GdipLoadImageFromFile")
	pGdipDisposeImage   = gdiplus.NewProc("GdipDisposeImage")
	pGdipCreateGraphics = gdiplus.NewProc("GdipCreateFromHDC")
	pGdipDeleteGraphics = gdiplus.NewProc("GdipDeleteGraphics")
	pGdipDrawImage      = gdiplus.NewProc("GdipDrawImageRectI")
	pGdipInterpolation = gdiplus.NewProc("GdipSetInterpolationMode")
	pDestroyWindow      = user32.NewProc("DestroyWindow")
	pPickerSaveDC       = syscall.NewLazyDLL("gdi32.dll").NewProc("SaveDC")
	pPickerRestoreDC    = syscall.NewLazyDLL("gdi32.dll").NewProc("RestoreDC")
	pPickerClipRect     = syscall.NewLazyDLL("gdi32.dll").NewProc("IntersectClipRect")
)

type gdipStartupInput struct {
	Version                  uint32
	DebugEventCallback       uintptr
	SuppressBackgroundThread int32
	SuppressExternalCodecs   int32
}
type pickerState struct {
	hwnd                               uintptr
	edition                            worldEdition
	roots                              string
	worlds                             []localWorld
	images                             []uintptr
	scroll, hover, selected            int
	w, h                               int
	gdipToken                          uintptr
	fontMain, fontSecondary, fontSmall uintptr
}

var picker pickerState
var pickerCallback uintptr
var pickerRegistered bool

const (
	pickerClass        = "MinecraftToBlenderWorldLibrary"
	pickerCardH        = 82
	pickerCardGap      = 9
	pickerListTop      = 142
	pickerFooterH      = 62
	wmLButtonDown      = 0x0201
	wmMouseWheelPicker = 0x020A
	vkEscape           = 0x1B
	vkReturn           = 0x0D
)

func openWorldLibrary(edition worldEdition) {
	if app.busy {
		return
	}
	if picker.hwnd != 0 {
		pDestroyWindow.Call(picker.hwnd)
	}
	picker = pickerState{edition: edition, selected: -1, hover: -1}
	picker.worlds = discoverWorlds(edition, "")
	showPickerWindow()
}
func pickerLoadImages() {
	if len(picker.worlds) == 0 {
		return
	}
	if picker.gdipToken == 0 {
		startup := gdipStartupInput{Version: 1}
		if status, _, _ := pGdiplusStartup.Call(uintptr(unsafe.Pointer(&picker.gdipToken)), uintptr(unsafe.Pointer(&startup)), 0); status != 0 {
			return
		}
	}
	picker.images = make([]uintptr, len(picker.worlds))
	for i, item := range picker.worlds {
		if item.icon == "" {
			continue
		}
		var h uintptr
		if status, _, _ := pGdipLoadImage.Call(ptr(item.icon), uintptr(unsafe.Pointer(&h))); status == 0 {
			picker.images[i] = h
		}
	}
}
func pickerRelease() {
	for _, v := range picker.images {
		if v != 0 {
			pGdipDisposeImage.Call(v)
		}
	}
	if picker.gdipToken != 0 {
		pGdiplusShutdown.Call(picker.gdipToken)
		picker.gdipToken = 0
	}
	for _, f := range []uintptr{picker.fontMain, picker.fontSecondary, picker.fontSmall} {
		if f != 0 {
			pDeleteObject.Call(f)
		}
	}
	picker.fontMain = 0
	picker.fontSecondary = 0
	picker.fontSmall = 0
	picker.hwnd = 0
	picker.images = nil
}
func pickerListHeight() int { return max(1, picker.h-pickerListTop-pickerFooterH) }
func pickerMaxScroll() int {
	total := len(picker.worlds) * (pickerCardH + pickerCardGap)
	return max(0, total-pickerListHeight()+4)
}
func pickerScroll(d int) {
	picker.scroll += d
	if picker.scroll < 0 {
		picker.scroll = 0
	}
	if picker.scroll > pickerMaxScroll() {
		picker.scroll = pickerMaxScroll()
	}
	if picker.hwnd != 0 {
		pInvalidate.Call(picker.hwnd, 0, 1)
	}
}
func pickerItemAt(x, y int) int {
	if x < 30 || x > picker.w-30 || y < pickerListTop || y > picker.h-pickerFooterH {
		return -1
	}
	yy := y - pickerListTop + picker.scroll
	i := yy / (pickerCardH + pickerCardGap)
	if i >= len(picker.worlds) || i < 0 || yy%(pickerCardH+pickerCardGap) >= pickerCardH {
		return -1
	}
	return i
}
func pickerSelect(idx int) {
	if idx < 0 || idx >= len(picker.worlds) {
		return
	}
	selected := picker.worlds[idx]
	app.selectedWorld = &selected
	// Always begin each world at the requested fixed origin. Users can
	// override either coordinate manually before starting an export.
	setText(app.ctrls[idX], "0")
	setText(app.ctrls[idZ], "0")
	if selected.edition == javaEdition {
		setText(app.ctrls[idMinY], "-64")
		setText(app.ctrls[idMaxY], "319")
	}
	name := safeExportName(selected.name)
	setText(app.ctrls[idName], name)
	setText(app.ctrls[idWorld], selected.path)
	// Keep the path available in compact mode and in the activity log.
	state(fmt.Sprintf("Selected %s world: %s", strings.Title(string(selected.edition)), selected.name))
	guiLog(fmt.Sprintf("Selected %s world: %s", selected.edition, selected.path))
	if selected.hasCenter {
		guiLog(fmt.Sprintf("World's recorded player/spawn location is X=%d Z=%d. Export center stays at X=0 Z=0 until you edit it.", selected.x, selected.z))
	}
	pDestroyWindow.Call(picker.hwnd)
	refreshButtons()
	pInvalidate.Call(app.main, 0, 1)
}
func safeExportName(s string) string {
	var b strings.Builder
	for _, r := range s {
		if r >= 'a' && r <= 'z' || r >= 'A' && r <= 'Z' || r >= '0' && r <= '9' || r == '_' {
			b.WriteRune(r)
		} else if (r == ' ' || r == '-' || r == '.') && b.Len() > 0 {
			b.WriteByte('_')
		}
		if b.Len() >= 56 {
			break
		}
	}
	name := strings.Trim(b.String(), "_")
	if name == "" {
		name = "Minecraft_World"
	}
	if name[0] >= '0' && name[0] <= '9' {
		name = "World_" + name
	}
	if !validateName(name) {
		name = "Minecraft_World"
	}
	return name
}
func pickerClick(x, y int) {
	if y >= picker.h-49 {
		if y <= picker.h-12 {
			switch {
			case x >= 27 && x <= 179:
				pickerBrowse()
			case x >= picker.w/2-62 && x <= picker.w/2+62:
				pickerRescan()
			case x >= picker.w-148 && x <= picker.w-27:
				pDestroyWindow.Call(picker.hwnd)
			}
		}
		return
	}
	if idx := pickerItemAt(x, y); idx >= 0 {
		pickerSelect(idx)
	}
}
func pickerBrowse() {
	directory := selectFolderTitle("Choose a Minecraft world folder or saves directory")
	if directory == "" {
		return
	}
	picker.roots = directory
	pickerRescan()
}
func pickerRescan() {
	pickerReleaseImages()
	picker.worlds = discoverWorlds(picker.edition, picker.roots)
	picker.scroll = 0
	picker.selected = -1
	picker.hover = -1
	pickerLoadImages()
	pInvalidate.Call(picker.hwnd, 0, 1)
}
func pickerReleaseImages() {
	for _, v := range picker.images {
		if v != 0 {
			pGdipDisposeImage.Call(v)
		}
	}
	picker.images = nil
}
func pickerProc(hwnd uintptr, m uint32, wp, lp uintptr) uintptr {
	switch m {
	case wmCreate:
		return 0
	case wmSize:
		picker.w = int(uint16(lp))
		picker.h = int(uint16(lp >> 16))
		pickerScroll(0)
		return 0
	case wmPaint:
		pickerPaint(hwnd)
		return 0
	case wmEraseBkgnd:
		return 1
	case wmLButtonDown:
		pickerClick(int(int16(uint16(lp))), int(int16(uint16(lp>>16))))
		return 0
	case wmMouseMove:
		idx := pickerItemAt(int(int16(uint16(lp))), int(int16(uint16(lp>>16))))
		if idx != picker.hover {
			picker.hover = idx
			pInvalidate.Call(hwnd, 0, 0)
		}
		return 0
	case wmMouseWheelPicker:
		delta := int16(uint16(wp >> 16))
		pickerScroll(-int(delta) * 4 / 3)
		return 0
	case wmKeyDown:
		switch wp {
		case vkEscape:
			pDestroyWindow.Call(hwnd)
		case vkReturn:
			if picker.selected >= 0 {
				pickerSelect(picker.selected)
			} else if len(picker.worlds) > 0 {
				pickerSelect(0)
			}
		case 0x26, 0x28:
			if wp == 0x26 {
				picker.selected = max(0, picker.selected-1)
			} else {
				picker.selected = min(len(picker.worlds)-1, picker.selected+1)
			}
			if picker.selected >= 0 {
				y := picker.selected * (pickerCardH + pickerCardGap)
				if y < picker.scroll {
					picker.scroll = y
				}
				if y+pickerCardH > picker.scroll+pickerListHeight() {
					picker.scroll = y + pickerCardH - pickerListHeight()
				}
			}
			pInvalidate.Call(hwnd, 0, 1)
		case 0x21:
			pickerScroll(-pickerListHeight())
		case 0x22:
			pickerScroll(pickerListHeight())
		}
		return 0
	case wmClose:
		pDestroyWindow.Call(hwnd)
		return 0
	case wmDestroy:
		pickerRelease()
		return 0
	}
	r, _, _ := pDefWndProc.Call(hwnd, uintptr(m), wp, lp)
	return r
}
func showPickerWindow() {
	inst, _, _ := pGetModule.Call()
	cname := w(pickerClass)
	if !pickerRegistered {
		pickerCallback = syscall.NewCallback(pickerProc)
		cursor, _, _ := pLoadCursor.Call(0, 32512)
		largeIcon, smallIcon := appIcons(inst)
		wc := wndClass{Size: uint32(unsafe.Sizeof(wndClass{})), WndProc: pickerCallback, Instance: inst, Icon: largeIcon, IconSm: smallIcon, Cursor: cursor, ClassName: cname}
		if registered, _, _ := pRegisterClass.Call(uintptr(unsafe.Pointer(&wc))); registered == 0 {
			alert("World picker unavailable", "Windows could not register the world selection window.", mbError)
			return
		}
		pickerRegistered = true
	}
	screenH := intSysMetric(1)
	screenW := intSysMetric(0)
	h := min(660, screenH-90)
	if h < 430 {
		h = 430
	}
	ww := min(780, screenW-60)
	if ww < 570 {
		ww = 570
	}
	hwnd, _, _ := pCreateWindow.Call(0, uintptr(unsafe.Pointer(cname)), ptr("Select Minecraft World"), uintptr(wsOverlappedWindow|wsVisible), uintptr((screenW-ww)/2), uintptr(max(0, (screenH-h)/2)), uintptr(ww), uintptr(h), app.main, 0, inst, 0)
	if hwnd == 0 {
		alert("Could not open world library", "Windows could not create the world selection window.", mbError)
		return
	}
	picker.hwnd = hwnd
	picker.fontMain = font("Segoe UI Semibold", -19, 600)
	picker.fontSecondary = font("Segoe UI", -15, 400)
	picker.fontSmall = font("Segoe UI", -13, 400)
	pickerLoadImages()
	pShowWindow.Call(hwnd, swShow)
	pUpdateWindow.Call(hwnd)
	pSetFocus.Call(hwnd)
	pInvalidate.Call(hwnd, 0, 1)
}
func intSysMetric(i int) int { n, _, _ := pGetSysMetrics.Call(uintptr(i)); return int(n) }
func pickerText(dc uintptr, s string, r rect, fg uint32, size int, align uintptr) {
	f := picker.fontSecondary
	if size == 0 {
		f = picker.fontMain
	} else if size == 2 {
		f = picker.fontSmall
	}
	buttonText(dc, s, r, fg, f, align)
}
func pickerPaint(hwnd uintptr) {
	var ps paintStruct
	dc, _, _ := pBeginPaint.Call(hwnd, uintptr(unsafe.Pointer(&ps)))
	defer pEndPaint.Call(hwnd, uintptr(unsafe.Pointer(&ps)))
	var bounds rect
	pGetClientRect.Call(hwnd, uintptr(unsafe.Pointer(&bounds)))
	ww, h := int(bounds.Right), int(bounds.Bottom)
	picker.w, picker.h = ww, h
	// Dark stone backdrop + Minecraft-grass green accent; text contrast is high.
	dark := color(25, 31, 30)
	panel := color(39, 47, 42)
	raised := color(50, 62, 53)
	green := color(83, 171, 69)
	muted := color(187, 201, 185)
	white := color(246, 250, 245)
	paintPill(dc, bounds, dark, 0)
	paintPill(dc, rect{0, 0, int32(ww), 7}, green, 0)
	editionName := "BEDROCK EDITION"
	if picker.edition == javaEdition {
		editionName = "JAVA EDITION"
	}
	pickerText(dc, "SELECT A WORLD", rect{32, 17, int32(ww - 25), 53}, white, 0, 0)
	pickerText(dc, editionName+"  •  Most recently played first", rect{32, 59, int32(ww - 25), 83}, muted, 1, 0)
	pickerText(dc, fmt.Sprintf("%d local worlds found", len(picker.worlds)), rect{32, 103, int32(ww - 25), 125}, green, 1, 0)
	if len(picker.worlds) == 0 {
		paintPill(dc, rect{30, 145, int32(ww - 30), int32(min(h-70, 315))}, panel, 10)
		pickerText(dc, "No worlds found automatically", rect{55, 166, int32(ww - 55), 208}, white, 0, dtCenter)
		pickerText(dc, "Use Choose folder for another launcher, drive or account.", rect{45, 210, int32(ww - 45), 248}, muted, 1, dtCenter)
	}
	// Clip partially visible world rows instead of hiding them completely.
	savedDC, _, _ := pPickerSaveDC.Call(dc)
	pPickerClipRect.Call(dc, 0, uintptr(pickerListTop), uintptr(ww), uintptr(max(pickerListTop, h-pickerFooterH)))
	var gdipGraphics uintptr
	if picker.gdipToken != 0 {
		pGdipCreateGraphics.Call(dc, uintptr(unsafe.Pointer(&gdipGraphics)))
	}
	step := pickerCardH + pickerCardGap
	first := max(0, picker.scroll/step-1)
	last := min(len(picker.worlds), (picker.scroll+pickerListHeight())/step+2)
	for i := first; i < last; i++ {
		v := picker.worlds[i]
		y := pickerListTop + i*step - picker.scroll
		if y+pickerCardH < pickerListTop || y > h-pickerFooterH {
			continue
		}
		fill := panel
		if i == picker.hover || i == picker.selected {
			fill = raised
		}
		paintPill(dc, rect{30, int32(y), int32(ww - 30), int32(y + pickerCardH)}, fill, 10)
		paintPill(dc, rect{39, int32(y + 10), 101, int32(y + 72)}, color(74, 106, 66), 4)
		if gdipGraphics != 0 && i < len(picker.images) && picker.images[i] != 0 {
			pGdipDrawImage.Call(gdipGraphics, picker.images[i], 39, uintptr(y+10), 62, 62)
		} else {
			// Native placeholder: grass/earth stripes (not redistributed game art).
			paintPill(dc, rect{45, int32(y + 17), 95, int32(y + 39)}, color(85, 153, 61), 0)
			paintPill(dc, rect{45, int32(y + 39), 95, int32(y + 65)}, color(116, 79, 48), 0)
		}
		pickerText(dc, v.name, rect{120, int32(y + 9), int32(ww - 62), int32(y + 34)}, white, 0, 0)
		when := "Date unavailable"
		if !v.played.IsZero() {
			when = v.played.Local().Format("Jan 2, 2006  3:04 PM")
		}
		label := "Last saved"
		if v.exactDate {
			label = "Last played"
		}
		pickerText(dc, label+": "+when, rect{120, int32(y + 40), int32(ww - 65), int32(y + 64)}, muted, 1, 0)
		if i == picker.hover || i == picker.selected {
			paintPill(dc, rect{int32(ww - 44), int32(y + 29), int32(ww - 40), int32(y + 54)}, green, 3)
		}
	}
	if gdipGraphics != 0 {
		pGdipDeleteGraphics.Call(gdipGraphics)
	}
	if savedDC != 0 {
		pPickerRestoreDC.Call(dc, savedDC)
	}
	// Footer gives custom-location support, refresh and cancel in same view.
	paintPill(dc, rect{0, int32(h - pickerFooterH), int32(ww), int32(h)}, color(32, 39, 35), 0)
	paintPill(dc, rect{27, int32(h - 49), 179, int32(h - 12)}, green, 6)
	pickerText(dc, "Choose folder", rect{29, int32(h - 47), 177, int32(h - 12)}, color(14, 31, 11), 1, dtCenter)
	paintPill(dc, rect{int32(ww/2 - 62), int32(h - 49), int32(ww/2 + 62), int32(h - 12)}, panel, 6)
	pickerText(dc, "Refresh", rect{int32(ww/2 - 60), int32(h - 47), int32(ww/2 + 60), int32(h - 12)}, white, 1, dtCenter)
	paintPill(dc, rect{int32(ww - 148), int32(h - 49), int32(ww - 27), int32(h - 12)}, panel, 6)
	pickerText(dc, "Cancel", rect{int32(ww - 146), int32(h - 47), int32(ww - 29), int32(h - 12)}, white, 1, dtCenter)
}

// compile-time guard used by code review for placeholder path handling
