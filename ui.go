//go:build windows

package main

import (
	"fmt"
	"strings"
	"syscall"
	"unsafe"
)

var (
	gdi              = syscall.NewLazyDLL("gdi32.dll")
	dwm              = syscall.NewLazyDLL("dwmapi.dll")
	pCreateFont      = gdi.NewProc("CreateFontW")
	pCreateBrush     = gdi.NewProc("CreateSolidBrush")
	pSelectObject    = gdi.NewProc("SelectObject")
	pDeleteObject    = gdi.NewProc("DeleteObject")
	pRoundRect       = gdi.NewProc("RoundRect")
	pFillRect        = user32.NewProc("FillRect")
	pDrawText        = user32.NewProc("DrawTextW")
	pDrawIconEx      = user32.NewProc("DrawIconEx")
	pSetTextColor    = gdi.NewProc("SetTextColor")
	pSetBkColor      = gdi.NewProc("SetBkColor")
	pSetBkMode       = gdi.NewProc("SetBkMode")
	pBeginPaint      = user32.NewProc("BeginPaint")
	pEndPaint        = user32.NewProc("EndPaint")
	pGetClientRect   = user32.NewProc("GetClientRect")
	pMoveWindow      = user32.NewProc("MoveWindow")
	pInvalidate      = user32.NewProc("InvalidateRect")
	pPostMessage     = user32.NewProc("PostMessageW")
	pLoadLibrary     = kernel32.NewProc("LoadLibraryW")
	pSetWindowLong   = user32.NewProc("SetWindowLongPtrW")
	pCallWindowProc  = user32.NewProc("CallWindowProcW")
	pGetSysMetrics   = user32.NewProc("GetSystemMetrics")
	pGetScrollInfo   = user32.NewProc("GetScrollInfo")
	pSetFocus        = user32.NewProc("SetFocus")
	pDwmSetAttribute = dwm.NewProc("DwmSetWindowAttribute")
	pTrackMouseEvent = user32.NewProc("TrackMouseEvent")
)

const (
	wmMouseWheel    = 0x020A
	wmMouseMove     = 0x0200
	wmMouseLeave    = 0x02A3
	wmVScroll       = 0x0115
	wmKeyDown       = 0x0100
	wmSetRedraw     = 0x000B
	swHide          = 0
	wsClipChildren  = 0x02000000
	bsOwnerDraw     = 0x0000000B
	emSetBkgndColor = 0x0443
	emSetCharFormat = 0x0444
	emExSetSel      = 0x0437
	emExGetSel      = 0x0434
	emReplaceSel    = 0x00C2
	emGetScrollPos  = 0x04DD
	emSetScrollPos  = 0x04DE
	sbBottom        = 7
	dtSingleLine    = 0x20
	dtVCenter       = 0x04
	dtCenter        = 0x01
	dtEndEllipsis   = 0x8000
	dtNoPrefix      = 0x0800
	cfmColor        = 0x40000000
	scfDefault      = 0
	odStateSelected = 0x0001
	odStateDisabled = 0x0004
	odStateFocus    = 0x0010
)

func color(r, g, b uint32) uint32 { return r | (g << 8) | (b << 16) }

// One neutral, high-contrast palette across the app. Blue indicates actions,
// while inactive/secondary controls use slate rather than competing colors.
var theme = struct{ bg, card, input, border, white, muted, quiet, accent, accentDark, second, danger, side, sideText, sideMuted, logBg, logText uint32 }{
	bg: color(244, 247, 251), card: color(255, 255, 255), input: color(239, 243, 249), border: color(222, 229, 238),
	white: color(15, 23, 42), muted: color(61, 77, 100), quiet: color(83, 100, 124),
	accent: color(37, 99, 235), accentDark: color(219, 233, 255), second: color(234, 240, 247), danger: color(165, 40, 46),
	side: color(255, 255, 255), sideText: color(30, 41, 59), sideMuted: color(81, 97, 119),
	logBg: color(17, 24, 39), logText: color(226, 234, 246),
}

type rect struct{ Left, Top, Right, Bottom int32 }
type paintStruct struct {
	Hdc       uintptr
	Erase     int32
	RcPaint   rect
	Restore   int32
	IncUpdate int32
	Reserved  [32]byte
}
type drawItem struct {
	Type, ID, Item, Action, State uint32
	Window, DC                    uintptr
	Rect                          rect
	Data                          uintptr
}
type point struct{ X, Y int32 }
type trackMouseEvent struct {
	Size, Flags       uint32
	Window, HoverTime uintptr
}
type charRange struct{ Min, Max int32 }
type charFormat struct {
	Size, Mask, Effects uint32
	Height, Offset      int32
	TextColor           uint32
	CharSet, Pitch      byte
	Face                [32]uint16
}
type scrollInfo struct {
	Size, Mask          uint32
	Min, Max            uint32
	Page, Pos, TrackPos uint32
}
type minmax struct{ Reserved, MaxSize, MaxPosition, MinTrack, MaxTrack point }
type textStyle struct{ fg, bg uint32 }

type uiState struct {
	tab                                                 int
	w, h                                                int
	cardTop, cardH                                      int
	activityTop, activityH                              int
	footerY                                             int
	fonts                                               [6]uintptr
	brushBg, brushCard, brushInput, brushSide, brushLog uintptr
	brandIcon                                           uintptr
	labels                                              map[uintptr]textStyle
	oldLogProc                                          uintptr
	oldButtonProc                                       uintptr
	buttonCallback                                      uintptr
	hoveredButton                                       uintptr
	progressFrame                                       int
	progressComplete                                    bool
	selectedImage, selectedImageToken                   uintptr
	selectedImagePath                                   string
	logCallback                                         uintptr
	rich                                                bool
	built                                               bool
}

var ui = uiState{labels: map[uintptr]textStyle{}}

func font(name string, h, weight int) uintptr {
	p, _, _ := pCreateFont.Call(uintptr(int32(h)), 0, 0, 0, uintptr(weight), 0, 0, 0, 1, 0, 0, 5, 0, ptr(name))
	return p
}
func applyFont(h, f uintptr) {
	if h != 0 {
		send(h, wmSetFont, f, 1)
	}
}
func show(id int, b bool) {
	h := app.ctrls[id]
	if h == 0 {
		return
	}
	flag := uintptr(swHide)
	if b {
		flag = swShow
	}
	pShowWindow.Call(h, flag)
}
func move(id, x, y, ww, hh int) {
	h := app.ctrls[id]
	if h == 0 {
		return
	}
	if ww < 10 {
		ww = 10
	}
	if hh < 10 {
		hh = 10
	}
	pMoveWindow.Call(h, uintptr(x), uintptr(y), uintptr(ww), uintptr(hh), 1)
}
func txt(s string, size int, strong bool, fg, bg uint32) uintptr {
	h := create("STATIC", s, 0, 0, 0, 20, 22, 0)
	idx := 1
	if size == 0 {
		idx = 0
	}
	if size == 2 {
		idx = 5
	}
	if size == 3 {
		idx = 3
	}
	if strong && size == 1 {
		idx = 2
	}
	applyFont(h, ui.fonts[idx])
	ui.labels[h] = textStyle{fg, bg}
	return h
}
func uiLabel(id int, s string, size int, fg, bg uint32) {
	h := txt(s, size, false, fg, bg)
	app.ctrls[id] = h
}
func uiField(id int, value string) {
	h := create("EDIT", value, wsTabStop|esAutoHScroll, 0, 0, 100, 29, id)
	send(h, 0x00D3, 0x3, uintptr(10|(10<<16))) // EM_SETMARGINS
	applyFont(h, ui.fonts[1])
	send(h, 0x00C5, 32767, 0) // EM_LIMITTEXT
}
func uiButton(id int, name string) {
	h := create("BUTTON", name, wsTabStop|bsOwnerDraw, 0, 0, 100, 32, id)
	applyFont(h, ui.fonts[2])
	if ui.buttonCallback == 0 {
		ui.buttonCallback = syscall.NewCallback(buttonWindowProc)
	}
	old, _, _ := pSetWindowLong.Call(h, ^uintptr(3), ui.buttonCallback) // GWLP_WNDPROC
	if ui.oldButtonProc == 0 {
		ui.oldButtonProc = old
	}
}
func buttonWindowProc(h uintptr, m uint32, wp, lp uintptr) uintptr {
	if m == wmMouseMove {
		if ui.hoveredButton != h {
			old := ui.hoveredButton
			ui.hoveredButton = h
			if old != 0 {
				pInvalidate.Call(old, 0, 1)
			}
			pInvalidate.Call(h, 0, 1)
		}
		ev := trackMouseEvent{Size: uint32(unsafe.Sizeof(trackMouseEvent{})), Flags: 0x2, Window: h}
		pTrackMouseEvent.Call(uintptr(unsafe.Pointer(&ev))) // TME_LEAVE
	} else if m == wmMouseLeave {
		if ui.hoveredButton == h {
			ui.hoveredButton = 0
			pInvalidate.Call(h, 0, 1)
		}
	}
	return callOriginalButton(h, m, wp, lp)
}
func callOriginalButton(h uintptr, m uint32, wp, lp uintptr) uintptr {
	if ui.oldButtonProc == 0 {
		return 0
	}
	r, _, _ := pCallWindowProc.Call(ui.oldButtonProc, h, uintptr(m), wp, lp)
	return r
}

const (
	uiBrand          = 190
	uiBrandSub       = 191
	uiNavHeader      = 192
	uiVersion        = 194
	uiExportStep     = 195
	uiTitle          = 200
	uiSubtitle       = 201
	uiExportTitle    = 202
	uiExportInfo     = 203
	uiWorldLabel     = 204
	uiNameLabel      = 205
	uiSizeLabel      = 206
	uiXLabel         = 207
	uiZLabel         = 208
	uiMinLabel       = 209
	uiMaxLabel       = 210
	uiImportTitle    = 212
	uiImportInfo     = 213
	uiUsdLabel       = 214
	uiBlenderLabel   = 215
	uiImportHint     = 216
	uiSettingsTitle  = 217
	uiSettingsInfo   = 218
	uiWorkspaceLabel = 219
	uiPrefsNote      = 220
	uiPacksHint      = 223
	uiAutoOpenHint   = 224
	uiActivityTitle  = 221
	uiActivityHint   = 222
)

func autoOpenBlenderLabel() string {
	if app.autoOpenBlender {
		return "Auto-open Blender: On"
	}
	return "Auto-open Blender: Off"
}

func createControls() {
	ui.fonts[0] = font("Segoe UI Semibold", -28, 650)
	ui.fonts[1] = font("Segoe UI", -16, 400)
	ui.fonts[2] = font("Segoe UI Semibold", -15, 600)
	ui.fonts[3] = font("Segoe UI", -14, 400)
	ui.fonts[4] = font("Consolas", -13, 400)
	ui.fonts[5] = font("Segoe UI Semibold", -20, 650)
	ui.brushBg, _, _ = pCreateBrush.Call(uintptr(theme.bg))
	ui.brushCard, _, _ = pCreateBrush.Call(uintptr(theme.card))
	ui.brushInput, _, _ = pCreateBrush.Call(uintptr(theme.input))
	ui.brushSide, _, _ = pCreateBrush.Call(uintptr(theme.side))
	ui.brushLog, _, _ = pCreateBrush.Call(uintptr(theme.logBg))

	uiLabel(uiBrand, "MINECRAFT", 2, theme.sideText, theme.side)
	uiLabel(uiBrandSub, "TO BLENDER", 3, theme.sideMuted, theme.side)
	uiLabel(uiNavHeader, "CONVERT", 3, theme.sideMuted, theme.side)
	uiLabel(uiTitle, "Export a Minecraft world", 0, theme.white, theme.bg)
	uiLabel(uiSubtitle, "Choose a Java or Bedrock save directly from your Minecraft world library.", 3, theme.muted, theme.bg)
	uiLabel(uiVersion, "VERSION 1", 3, theme.accent, theme.bg)
	uiButton(idTabExport, "Export world")
	uiButton(idTabImport, "Import USD")
	uiButton(idTabSettings, "Settings")

	uiLabel(uiExportStep, "NEW EXPORT", 3, theme.accent, theme.card)
	uiLabel(uiExportTitle, "Minecraft world", 2, theme.white, theme.card)
	uiLabel(uiExportInfo, "The export can go straight into Blender when finished.", 3, theme.muted, theme.card)
	uiLabel(uiWorldLabel, "SELECT A WORLD FROM YOUR LOCAL SAVES", 3, theme.muted, theme.card)
	uiButton(idSelectBedrock, "Select Bedrock World")
	uiButton(idSelectJava, "Select Java World")
	uiField(idWorld, "No world selected")
	send(app.ctrls[idWorld], 0x00CF, 1, 0) // EM_SETREADONLY

	for _, p := range []struct {
		id    int
		label string
	}{
		{uiNameLabel, "EXPORT NAME"}, {uiSizeLabel, "AREA / BLOCKS"}, {uiXLabel, "CENTER X"},
		{uiZLabel, "CENTER Z"}, {uiMinLabel, "MIN HEIGHT"}, {uiMaxLabel, "MAX HEIGHT"},
	} {
		uiLabel(p.id, p.label, 3, theme.muted, theme.card)
	}
	uiField(idName, "Bedrock_World")
	uiField(idSize, "512")
	uiField(idX, "0")
	uiField(idZ, "0")
	uiField(idMinY, "-64")
	uiField(idMaxY, "319")
	uiButton(idBoth, "Export to Blender")
	uiButton(idExport, "USD only")

	uiLabel(uiImportTitle, "Existing MiEx export", 2, theme.white, theme.card)
	uiLabel(uiImportInfo, "Already have a USD? Skip the world export.", 3, theme.muted, theme.card)
	uiLabel(uiUsdLabel, "MAIN MIEX USD FILE", 3, theme.muted, theme.card)
	uiField(idUSD, "")
	uiButton(idUSDBrowse, "Browse")
	uiLabel(uiBlenderLabel, "BLENDER INSTALLATION", 3, theme.muted, theme.card)
	uiField(idBlender, detectBlender())
	uiButton(idBlenderBrowse, "Browse")
	uiLabel(uiImportHint, "Saves a new .blend beside the USD. Original files remain untouched.", 3, theme.quiet, theme.card)
	uiButton(idImport, "Create Blender project")

	uiLabel(uiSettingsTitle, "App settings", 2, theme.white, theme.card)
	uiLabel(uiSettingsInfo, "Choose your workspace and export preferences.", 3, theme.muted, theme.card)
	uiLabel(uiWorkspaceLabel, "WORKSPACE FOLDER", 3, theme.muted, theme.card)
	uiField(idWorkspace, defaultWorkspace())
	uiButton(idWorkspaceBrowse, "Browse")
	uiButton(idWorldPacks, "Use world resource packs: Off")
	uiLabel(uiPacksHint, "Off by default. Uses packs supplied with the world when available.", 3, theme.quiet, theme.card)
	uiButton(idAutoOpenBlender, autoOpenBlenderLabel())
	uiLabel(uiAutoOpenHint, "Open the saved .blend after a successful import.", 3, theme.quiet, theme.card)
	uiLabel(uiPrefsNote, "Java 21+ and Blender required. Original world saves stay unchanged.", 3, theme.muted, theme.card)

	uiLabel(uiActivityTitle, "Activity", 2, theme.white, theme.card)
	uiLabel(uiActivityHint, "Detailed conversion log", 3, theme.muted, theme.card)
	uiButton(idFollow, "Following")
	uiLabel(idStatus, "Ready to export or import.", 3, theme.muted, theme.card)
	create("msctls_progress32", "", pbsMarquee, 0, 0, 100, 5, idProgress)
	pLoadLibrary.Call(ptr("Msftedit.dll"))
	logWnd := create("RICHEDIT50W", "", wsVScroll|esMultiline|esReadOnly|esAutoVScroll, 0, 0, 200, 110, idLog)
	if logWnd == 0 {
		logWnd = create("EDIT", "", wsVScroll|esMultiline|esReadOnly|esAutoVScroll, 0, 0, 200, 110, idLog)
		send(logWnd, 0x00C5, 16*1024*1024, 0) // EM_LIMITTEXT
	} else {
		ui.rich = true
	}
	applyFont(logWnd, ui.fonts[4])
	if ui.rich {
		send(logWnd, 0x0435, 0, 16*1024*1024)
		send(logWnd, emSetBkgndColor, 0, uintptr(theme.logBg))
		cf := charFormat{Size: uint32(unsafe.Sizeof(charFormat{})), Mask: cfmColor, TextColor: theme.logText}
		send(logWnd, emSetCharFormat, scfDefault, uintptr(unsafe.Pointer(&cf)))
		ui.logCallback = syscall.NewCallback(logWindowProc)
		old, _, _ := pSetWindowLong.Call(logWnd, ^uintptr(3), ui.logCallback)
		ui.oldLogProc = old
	}
	uiButton(idFolder, "Output folder")
	uiButton(idBlendOpen, "Open project")
	uiButton(idCancel, "Cancel")
	enabled(idCancel, false)
	enabled(idBlendOpen, false)
	app.followLog = true
	ui.built = true
	layoutUI()
	refreshButtons()
}

func layoutUI() {
	if app.main == 0 || !ui.built {
		return
	}
	var r rect
	pGetClientRect.Call(app.main, uintptr(unsafe.Pointer(&r)))
	ui.w, ui.h = int(r.Right), int(r.Bottom)
	W, H := ui.w, ui.h
	if W < 650 || H < 420 {
		return
	}
	side := 205
	contentX := side + 27
	contentR := W - 25
	contentW := contentR - contentX
	compact := H < 644
	ui.cardTop = 102
	ui.cardH = 390
	if compact {
		ui.cardH = 322
	}
	ui.activityTop = ui.cardTop + ui.cardH + 12
	ui.footerY = H - 20
	ui.activityH = ui.footerY - ui.activityTop - 10
	if ui.activityH < 90 {
		ui.activityH = 90
	}

	move(uiBrand, 55, 28, 145, 28)
	move(uiBrandSub, 22, 69, 175, 19)
	move(uiNavHeader, 22, 119, 167, 22)
	for i, id := range []int{idTabExport, idTabImport, idTabSettings} {
		move(id, 13, 148+i*53, 179, 46)
	}
	// Quick access header is drawn once by paintMain, avoiding a stale label control.
	if app.lastBlend != "" {
		move(idFolder, 14, H-135, 175, 42)
		move(idBlendOpen, 14, H-84, 175, 42)
	} else {
		move(idFolder, 14, H-84, 175, 42)
	}
	show(idBlendOpen, !app.busy && app.lastBlend != "")

	move(uiTitle, contentX, 23, contentW-5, 37)
	move(uiSubtitle, contentX, 66, contentW-5, 22)
	move(uiVersion, contentR-135, 9, 135, 19)

	x := contentX + 22
	w := contentW - 44
	top := ui.cardTop
	move(uiExportStep, x, top+12, w, 18)
	if compact {
		move(uiExportTitle, x, top+16, w, 30)
	} else {
		move(uiExportTitle, x, top+37, w, 29)
	}
	move(uiExportInfo, x, top+69, w, 19)
	move(uiWorldLabel, x, top+95, w, 18)
	fw := w - 102
	// Highlight the selected edition; retain the path field in compact mode.
	move(idSelectBedrock, x, top+117, (w-12)/2, 37)
	move(idSelectJava, x+(w-12)/2+12, top+117, (w-12)/2, 37)
	// The expanded layout shows a thumbnail/name/date card instead of a path.
	// The original read-only path control remains available in compact mode.
	move(idWorld, x, top+159, w, 36)
	show(idWorldBrowse, false)
	labels := []int{uiNameLabel, uiSizeLabel, uiXLabel, uiZLabel, uiMinLabel, uiMaxLabel}
	fields := []int{idName, idSize, idX, idZ, idMinY, idMaxY}
	if compact {
		gap := 12
		cw := (w - 2*gap) / 3
		for i := range fields {
			col, row := i%3, i/3
			xx := x + col*(cw+gap)
			yy := top + 160 + row*52
			ww := cw
			if col == 2 {
				ww = x + w - xx
			}
			move(labels[i], xx, yy, ww, 17)
			move(fields[i], xx, yy+18, ww, 32)
		}
		pw := (w * 61) / 100
		if pw < 198 {
			pw = 198
		}
		move(idBoth, x, top+269, pw, 39)
		move(idExport, x+pw+10, top+269, w-pw-10, 39)
		move(uiWorldLabel, x, top+49, w, 17)
		move(idSelectBedrock, x, top+71, (w-12)/2, 37)
		move(idSelectJava, x+(w-12)/2+12, top+71, (w-12)/2, 37)
		move(idWorld, x, top+115, w, 31)
		show(uiExportStep, false)
		show(uiExportInfo, false)
	} else {
		gap := 13
		cw := (w - 2*gap) / 3
		for i := range fields {
			col, row := i%3, i/3
			xx := x + col*(cw+gap)
			yy := top + 217 + row*58
			ww := cw
			if col == 2 {
				ww = x + w - xx
			}
			move(labels[i], xx, yy, ww, 18)
			move(fields[i], xx, yy+19, ww, 35)
		}
		pw := (w * 65) / 100
		if pw < 220 {
			pw = 220
		}
		move(idBoth, x, top+335, pw, 44)
		move(idExport, x+pw+8, top+335, w-pw-8, 44)
		show(uiExportInfo, true)
	}

	if compact {
		move(uiImportTitle, x, top+22, w, 30)
		move(uiImportInfo, x, top+53, w, 20)
		move(uiUsdLabel, x, top+72, w, 18)
		move(idUSD, x, top+94, fw, 36)
		move(idUSDBrowse, x+fw+10, top+92, 92, 42)
		move(uiBlenderLabel, x, top+141, w, 18)
		move(idBlender, x, top+163, fw, 36)
		move(idBlenderBrowse, x+fw+10, top+161, 92, 42)
		move(idImport, x, top+220, w, 49)
		move(uiImportHint, x, top+260, w, 18)
	} else {
		move(uiImportTitle, x, top+34, w, 30)
		move(uiImportInfo, x, top+69, w, 22)
		move(uiUsdLabel, x, top+95, w, 20)
		move(idUSD, x, top+119, fw, 39)
		move(idUSDBrowse, x+fw+10, top+117, 92, 44)
		move(uiBlenderLabel, x, top+172, w, 20)
		move(idBlender, x, top+195, fw, 39)
		move(idBlenderBrowse, x+fw+10, top+193, 92, 44)
		move(uiImportHint, x, top+244, w, 20)
		move(idImport, x, top+281, w, 51)
	}

	if compact {
		move(uiSettingsTitle, x, top+16, w, 28)
		move(uiSettingsInfo, x, top+49, w, 20)
		move(uiWorkspaceLabel, x, top+83, w, 18)
		move(idWorkspace, x, top+106, fw, 35)
		move(idWorkspaceBrowse, x+fw+10, top+104, 92, 39)
		move(idWorldPacks, x, top+153, w, 37)
		move(uiPacksHint, x, top+194, w, 18)
		move(idAutoOpenBlender, x, top+224, w, 37)
		move(uiAutoOpenHint, x, top+263, w, 18)
		move(uiPrefsNote, x, top+287, w, 29)
	} else {
		move(uiSettingsTitle, x, top+34, w, 30)
		move(uiSettingsInfo, x, top+69, w, 20)
		move(uiWorkspaceLabel, x, top+101, w, 20)
		move(idWorkspace, x, top+125, fw, 40)
		move(idWorkspaceBrowse, x+fw+10, top+123, 92, 44)
		move(idWorldPacks, x, top+177, w, 40)
		move(uiPacksHint, x, top+222, w, 19)
		move(idAutoOpenBlender, x, top+254, w, 40)
		move(uiAutoOpenHint, x, top+298, w, 19)
		move(uiPrefsNote, x, top+324, w, 48)
	}

	a := ui.activityTop
	move(uiActivityTitle, x, a+11, 122, 26)
	move(uiActivityHint, x+114, a+16, w-270, 19)
	move(idFollow, contentR-137, a+9, 115, 31)
	move(idCancel, contentR-255, a+9, 108, 31)
	show(idCancel, app.busy)
	move(idStatus, x, a+46, w, 23)
	show(idProgress, false)
	move(idProgress, x, a+76, w, 7)
	logTop := a + 91
	logH := ui.activityH - 98
	if logH < 24 {
		logH = 24
	}
	move(idLog, x+8, logTop, w-16, logH)

	for _, id := range []int{uiExportStep, uiExportTitle, uiExportInfo, uiWorldLabel, idSelectBedrock, idSelectJava, uiNameLabel, uiSizeLabel, uiXLabel, uiZLabel, uiMinLabel, uiMaxLabel, idWorld, idWorldBrowse, idName, idSize, idX, idZ, idMinY, idMaxY, idExport, idBoth} {
		show(id, ui.tab == 0 && !(compact && (id == uiExportStep || id == uiExportInfo)) && (id != idWorld || compact))
	}
	for _, id := range []int{uiImportTitle, uiImportInfo, uiUsdLabel, uiBlenderLabel, uiImportHint, idUSD, idUSDBrowse, idBlender, idBlenderBrowse, idImport} {
		show(id, ui.tab == 1 && (!compact || (id != uiImportHint && id != uiImportInfo)))
	}
	for _, id := range []int{uiSettingsTitle, uiSettingsInfo, uiWorkspaceLabel, uiPrefsNote, uiPacksHint, uiAutoOpenHint, idWorkspace, idWorkspaceBrowse, idWorldPacks, idAutoOpenBlender} {
		show(id, ui.tab == 2)
	}
	// In compact mode these actions sit near the bottom of the setup card.
	pInvalidate.Call(app.main, 0, 1)
}

func switchTab(id int) {
	switch id {
	case idTabExport:
		ui.tab = 0
	case idTabImport:
		ui.tab = 1
	case idTabSettings:
		ui.tab = 2
	}
	switch ui.tab {
	case 0:
		setText(app.ctrls[uiTitle], "Export a Minecraft world")
		setText(app.ctrls[uiSubtitle], "Choose a Java or Bedrock world, adjust the region, and create a Blender project.")
	case 1:
		setText(app.ctrls[uiTitle], "Import into Blender")
		setText(app.ctrls[uiSubtitle], "Turn an existing MiEx USD into a Blender project without re-exporting.")
	case 2:
		setText(app.ctrls[uiTitle], "Settings & workspace")
		setText(app.ctrls[uiSubtitle], "Choose where exports, tools, and completed models are saved.")
	}
	layoutUI()
	refreshButtons()
}
func refreshButtons() {
	for _, id := range []int{idTabExport, idTabImport, idTabSettings, idExport, idBoth, idImport, idCancel, idFollow, idSelectBedrock, idSelectJava, idWorldPacks, idAutoOpenBlender, idWorldBrowse, idUSDBrowse, idBlenderBrowse, idWorkspaceBrowse, idFolder, idBlendOpen} {
		if h := app.ctrls[id]; h != 0 {
			pInvalidate.Call(h, 0, 1)
		}
	}
}
// paintPill draws a filled rounded button with no border, stroke or focus outline.
// We retain a standard BUTTON control (with OwnerDraw) for keyboard, tab and
// accessibility behavior, while the appearance is fully painted here.
func paintPill(dc uintptr, r rect, fill uint32, corner int) {
	brush, _, _ := pCreateBrush.Call(uintptr(fill))
	nullPen, _, _ := pGetStockObject.Call(8) // NULL_PEN: no visible or hidden outline.
	oldBrush, _, _ := pSelectObject.Call(dc, brush)
	oldPen, _, _ := pSelectObject.Call(dc, nullPen)
	pRoundRect.Call(dc, uintptr(r.Left), uintptr(r.Top), uintptr(r.Right), uintptr(r.Bottom), uintptr(corner), uintptr(corner))
	pSelectObject.Call(dc, oldPen)
	pSelectObject.Call(dc, oldBrush)
	pDeleteObject.Call(brush)
}
func mix(c uint32, r, g, b uint32) uint32 {
	red := uint32(c & 255)
	green := uint32((c >> 8) & 255)
	blue := uint32((c >> 16) & 255)
	return color((red*3+r)/4, (green*3+g)/4, (blue*3+b)/4)
}
func buttonText(dc uintptr, t string, r rect, fg uint32, f uintptr, align uintptr) {
	pSetBkMode.Call(dc, 1)
	pSetTextColor.Call(dc, uintptr(fg))
	old, _, _ := pSelectObject.Call(dc, f)
	pDrawText.Call(dc, ptr(t), ^uintptr(0), uintptr(unsafe.Pointer(&r)), align|dtVCenter|dtSingleLine|dtNoPrefix|dtEndEllipsis)
	pSelectObject.Call(dc, old)
}

// Simple, consistent Win32 owner-drawn buttons. Every control is borderless;
// selection/focus is communicated by fill and text contrast, not a focus box.
func paintButton(lp uintptr) uintptr {
	d := (*drawItem)(unsafe.Pointer(lp))
	id, r := int(d.ID), d.Rect
	nav := id == idTabExport || id == idTabImport || id == idTabSettings
	active := (id == idTabExport && ui.tab == 0) || (id == idTabImport && ui.tab == 1) || (id == idTabSettings && ui.tab == 2)
	primary := id == idBoth || id == idImport
	selectedEdition := app.selectedWorld != nil &&
		((id == idSelectBedrock && app.selectedWorld.edition == bedrockEdition) ||
			(id == idSelectJava && app.selectedWorld.edition == javaEdition))
	browse := id == idWorldBrowse || id == idUSDBrowse || id == idBlenderBrowse || id == idWorkspaceBrowse
	sideAction := id == idFolder || id == idBlendOpen
	disabled := d.State&odStateDisabled != 0
	hover := !disabled && ui.hoveredButton == d.Window
	pressed := !disabled && d.State&odStateSelected != 0
	focused := !disabled && d.State&odStateFocus != 0
	// Clear the WHOLE control first. Painting only a rounded rectangle leaves
	// the native Windows button background visible at the four corners.
	parentBrush := ui.brushCard
	if nav || sideAction {
		parentBrush = ui.brushSide
	}
	pFillRect.Call(d.DC, uintptr(unsafe.Pointer(&r)), parentBrush)

	fill, fg, radius := theme.second, theme.white, 12
	if nav {
		fill, fg, radius = theme.side, theme.sideText, 10
		if active {
			fill, fg = theme.accentDark, color(29, 78, 179)
		}
		if (hover || focused) && !active {
			fill = theme.input
		}
		if pressed {
			fill = color(210, 225, 248)
		}
	} else if (id == idWorldPacks && app.useWorldPacks) || (id == idAutoOpenBlender && app.autoOpenBlender) {
		fill, fg = theme.accentDark, color(29, 78, 179)
		if hover || focused {
			fill = color(200, 223, 255)
		}
	} else if selectedEdition {
		fill, fg = theme.accentDark, color(29, 78, 179)
		if hover || focused {
			fill = color(200, 223, 255)
		}
		if pressed {
			fill = color(182, 211, 251)
		}
	} else if primary {
		fill, fg = theme.accent, color(255, 255, 255)
		if hover || focused {
			fill = color(29, 78, 216)
		}
		if pressed {
			fill = color(30, 64, 175)
		}
	} else if sideAction {
		fill, fg, radius = theme.side, theme.sideText, 10
		if hover || focused {
			fill = theme.input
		}
		if pressed {
			fill = theme.second
		}
	} else if id == idCancel {
		fill, fg = color(254, 239, 239), theme.danger
		if hover || focused {
			fill = color(253, 226, 226)
		}
		if pressed {
			fill = color(250, 210, 211)
		}
	} else {
		if hover || focused {
			fill = color(221, 232, 244)
		}
		if pressed {
			fill = color(206, 221, 238)
		}
		if browse {
			radius = 10
		}
	}
	if disabled {
		fill, fg = theme.input, color(119, 131, 149)
	}
	// Maintain uniform 1px inset to eliminate edge artifacts at small sizes.
	content := rect{r.Left + 1, r.Top + 1, r.Right - 1, r.Bottom - 1}
	if nav || sideAction {
		if active || hover || focused || pressed {
			paintPill(d.DC, content, fill, radius)
		}
	} else {
		paintPill(d.DC, content, fill, radius)
	}
	textArea := r
	if nav || sideAction {
		textArea.Left += 17
		textArea.Right -= 8
	}
	align := uintptr(dtCenter)
	if nav || sideAction {
		align = 0
	}
	buttonText(d.DC, getText(id), textArea, fg, ui.fonts[2], align)
	if active {
		// Accent stripe is only on the active navigation row.
		paintPill(d.DC, rect{r.Left + 3, r.Top + 11, r.Left + 6, r.Bottom - 11}, theme.accent, 3)
	}
	return 1
}

func colorControl(m uint32, wp, lp uintptr) uintptr {
	if m == wmColorStatic {
		if st, ok := ui.labels[lp]; ok {
			pSetTextColor.Call(wp, uintptr(st.fg))
			pSetBkColor.Call(wp, uintptr(st.bg))
			pSetBkMode.Call(wp, 1)
			switch st.bg {
			case theme.bg:
				return ui.brushBg
			case theme.side:
				return ui.brushSide
			default:
				return ui.brushCard
			}
		}
	}
	if lp == app.ctrls[idLog] {
		pSetTextColor.Call(wp, uintptr(theme.logText))
		pSetBkColor.Call(wp, uintptr(theme.logBg))
		return ui.brushLog
	}
	pSetTextColor.Call(wp, uintptr(theme.white))
	pSetBkColor.Call(wp, uintptr(theme.input))
	return ui.brushInput
}

func paintMain(h uintptr) {
	var ps paintStruct
	dc, _, _ := pBeginPaint.Call(h, uintptr(unsafe.Pointer(&ps)))
	var r rect
	pGetClientRect.Call(h, uintptr(unsafe.Pointer(&r)))
	pFillRect.Call(dc, uintptr(unsafe.Pointer(&r)), ui.brushBg)
	sideRect := rect{0, 0, 205, int32(ui.h)}
	pFillRect.Call(dc, uintptr(unsafe.Pointer(&sideRect)), ui.brushSide)
	// Reuse the EXE logo in the sidebar; retain the original marker if Windows cannot draw it.
	if ui.brandIcon == 0 {
		paintPill(dc, rect{19, 25, 46, 54}, theme.accent, 9)
	} else if ok, _, _ := pDrawIconEx.Call(dc, 19, 25, ui.brandIcon, 29, 29, 0, 0, 3); ok == 0 {
		paintPill(dc, rect{19, 25, 46, 54}, theme.accent, 9)
	}
	footerHeader := ui.h - 118
	if app.lastBlend != "" && !app.busy {
		footerHeader = ui.h - 170
	}
	buttonText(dc, "QUICK ACCESS", rect{22, int32(footerHeader), 190, int32(footerHeader + 20)}, theme.sideMuted, ui.fonts[3], 0)
	// A calm, lightly elevated main setup surface replaces the old outlined tab box.
	cx := int32(205 + 27)
	right := int32(ui.w - 25)
	card := rect{cx, int32(ui.cardTop), right, int32(ui.cardTop + ui.cardH)}
	paintPill(dc, rect{card.Left, card.Top + 3, card.Right, card.Bottom + 3}, color(231, 236, 244), 20)
	paintPill(dc, card, theme.card, 20)
	if ui.tab == 0 && ui.h >= 644 {
		paintSelectedWorld(dc, rect{cx + 22, int32(ui.cardTop + 161), right - 22, int32(ui.cardTop + 210)})
	}
	activity := rect{cx, int32(ui.activityTop), right, int32(ui.activityTop + ui.activityH)}
	paintPill(dc, rect{activity.Left, activity.Top + 2, activity.Right, activity.Bottom + 2}, color(231, 236, 244), 20)
	paintPill(dc, activity, theme.card, 20)
	// Progress is real activity (marquee); percentage is intentionally omitted.
	px := int(cx) + 22
	pw := int(right-cx) - 44
	py := ui.activityTop + 76
	if pw > 50 {
		paintPill(dc, rect{int32(px), int32(py), int32(px + pw), int32(py + 7)}, theme.input, 7)
		if app.busy {
			length := pw / 5
			if length < 50 {
				length = 50
			}
			offset := (ui.progressFrame*11)%(pw+length) - length
			left := px + offset
			rightX := left + length
			if left < px {
				left = px
			}
			if rightX > px+pw {
				rightX = px + pw
			}
			if rightX > left {
				paintPill(dc, rect{int32(left), int32(py), int32(rightX), int32(py + 7)}, theme.accent, 7)
			}
		} else if ui.progressComplete {
			paintPill(dc, rect{int32(px), int32(py), int32(px + pw), int32(py + 7)}, theme.accent, 7)
		}
	}
	pEndPaint.Call(h, uintptr(unsafe.Pointer(&ps)))
}

// The main selected-world preview keeps the Minecraft icon and the useful
// information visible after the world picker closes, without a giant path field.
func paintSelectedWorld(dc uintptr, area rect) {
	paintPill(dc, area, theme.input, 11)
	left := area.Left + 9
	icon := rect{left, area.Top + 5, left + 39, area.Bottom - 5}
	paintPill(dc, icon, color(203, 216, 234), 6)
	item := app.selectedWorld
	name := "No world selected"
	info := "Choose a Bedrock or Java save above to begin."
	if item != nil {
		name = item.name
		if name == "" {
			name = "Unnamed world"
		}
		edition := "Bedrock Edition"
		if item.edition == javaEdition {
			edition = "Java Edition"
		}
		info = edition
		if !item.played.IsZero() {
			when := "Last saved"
			if item.exactDate {
				when = "Last played"
			}
			info += "  ·  " + when + " " + item.played.Format("Jan 2, 2006")
		} else {
			info += "  ·  Date unavailable"
		}
		loadSelectedImage(item.icon)
		if ui.selectedImage != 0 {
			var graphics uintptr
			if code, _, _ := pGdipCreateGraphics.Call(dc, uintptr(unsafe.Pointer(&graphics))); code == 0 && graphics != 0 {
				pGdipDrawImage.Call(graphics, ui.selectedImage, uintptr(icon.Left), uintptr(icon.Top), uintptr(icon.Right-icon.Left), uintptr(icon.Bottom-icon.Top))
				pGdipDeleteGraphics.Call(graphics)
			}
		}
	} else {
		loadSelectedImage("")
	}
	buttonText(dc, name, rect{left + 49, area.Top + 4, area.Right - 11, area.Top + 25}, theme.white, ui.fonts[2], 0)
	buttonText(dc, info, rect{left + 49, area.Top + 25, area.Right - 11, area.Bottom - 2}, theme.muted, ui.fonts[3], 0)
}

func releaseSelectedImage() {
	if ui.selectedImage != 0 {
		pGdipDisposeImage.Call(ui.selectedImage)
		ui.selectedImage = 0
	}
	if ui.selectedImageToken != 0 {
		pGdiplusShutdown.Call(ui.selectedImageToken)
		ui.selectedImageToken = 0
	}
	ui.selectedImagePath = ""
}

func loadSelectedImage(path string) {
	if path == ui.selectedImagePath {
		return
	}
	if ui.selectedImage != 0 {
		pGdipDisposeImage.Call(ui.selectedImage)
		ui.selectedImage = 0
	}
	ui.selectedImagePath = path
	if path == "" {
		return
	}
	if ui.selectedImageToken == 0 {
		startup := gdipStartupInput{Version: 1}
		if code, _, _ := pGdiplusStartup.Call(uintptr(unsafe.Pointer(&ui.selectedImageToken)), uintptr(unsafe.Pointer(&startup)), 0); code != 0 {
			return
		}
	}
	var img uintptr
	if code, _, _ := pGdipLoadImage.Call(ptr(path), uintptr(unsafe.Pointer(&img))); code == 0 {
		ui.selectedImage = img
	}
}

func setMinimumSize(lp uintptr) {
	mi := (*minmax)(unsafe.Pointer(lp))
	mi.MinTrack = point{810, 570}
}

func resetLog() {
	// Drain messages from the previous completed process before a new run.
	// Otherwise a delayed UI tick could mix two conversions' logs.
	for len(app.logCh) > 0 {
		<-app.logCh
	}
	droppedLogLines.Store(0)
	app.logLines = nil
	app.logShown = 0
	app.followLog = true
	if h := app.ctrls[idLog]; h != 0 {
		setText(h, "")
	}
	setText(app.ctrls[idFollow], "Following")
	refreshButtons()
}
func logWindowProc(h uintptr, m uint32, wp, lp uintptr) uintptr {
	isInteraction := m == wmMouseWheel || m == wmVScroll || m == wmKeyDown
	if isInteraction {
		switch m {
		case wmMouseWheel:
			delta := int16(uint16(wp >> 16))
			if delta > 0 {
				app.followLog = false
			}
		case wmVScroll:
			op := wp & 0xffff
			if op == 0 || op == 2 || op == 5 || op == 4 {
				app.followLog = false
			}
		case wmKeyDown:
			if wp == 0x26 || wp == 0x21 || wp == 0x24 {
				app.followLog = false
			} // Up, PageUp, Home
		}
	}
	r, _, _ := pCallWindowProc.Call(ui.oldLogProc, h, uintptr(m), wp, lp)
	if isInteraction {
		pPostMessage.Call(app.main, wmLogScrollChanged, 0, 0)
	}
	return r
}
func logAtBottom() bool {
	h := app.ctrls[idLog]
	if h == 0 {
		return true
	}
	v := scrollInfo{Size: uint32(unsafe.Sizeof(scrollInfo{})), Mask: 0x17}
	ok, _, _ := pGetScrollInfo.Call(h, 1, uintptr(unsafe.Pointer(&v)))
	if ok == 0 {
		return app.followLog
	}
	bottom := int64(v.Max) - int64(v.Page) + 1
	if bottom < 0 {
		bottom = 0
	}
	return int64(v.Pos) >= bottom-2
}
func updateFollowUI() {
	if app.followLog {
		setText(app.ctrls[idFollow], "Following")
	} else {
		setText(app.ctrls[idFollow], "Latest ↓")
	}
	if h := app.ctrls[idFollow]; h != 0 {
		pInvalidate.Call(h, 0, 1)
	}
}
func updateFollowFromScroll() {
	if logAtBottom() {
		app.followLog = true
	} else {
		app.followLog = false
	}
	updateFollowUI()
}
func resumeFollowing() {
	app.followLog = true
	send(app.ctrls[idLog], wmVScroll, sbBottom, 0)
	updateFollowUI()
}
func updateLog() {
	h := app.ctrls[idLog]
	if h == 0 {
		return
	}
	if app.logShown < 0 || app.logShown > len(app.logLines) {
		app.logShown = 0
		setText(h, "")
	}
	if app.logShown == len(app.logLines) {
		return
	}
	var chunkBuilder strings.Builder
	for _, l := range app.logLines[app.logShown:] {
		chunkBuilder.WriteString(l)
		chunkBuilder.WriteString("\r\n")
	}
	chunk := chunkBuilder.String()
	app.logShown = len(app.logLines)
	if !ui.rich {
		// Standard EDIT can append new log text without retrieving and rewriting
		// everything displayed so far. Respect its 16 MiB EM_LIMITTEXT cap:
		// above that threshold, retain the original WM_SETTEXT behavior.
		oldFirst := send(h, 0x00CE, 0, 0) // EM_GETFIRSTVISIBLELINE
		currentLength := send(h, 0x000E, 0, 0) // WM_GETTEXTLENGTH
		if app.followLog && currentLength+uintptr(len(chunk)) < 16*1024*1024 {
			send(h, 0x00B1, ^uintptr(0), ^uintptr(0)) // EM_SETSEL
			send(h, emReplaceSel, 0, ptr(chunk))
			send(h, 0x00B7, 0, 0) // EM_SCROLLCARET
		} else {
			// This path also preserves scroll position while follow is paused.
			setText(h, getText(idLog)+chunk)
			if app.followLog {
				send(h, 0x00B1, ^uintptr(0), ^uintptr(0))
				send(h, 0x00B7, 0, 0)
			} else {
				now := send(h, 0x00CE, 0, 0)
				send(h, 0x00B6, uintptr(int32(oldFirst)-int32(now)), 0) // EM_LINESCROLL
			}
		}
		return
	}
	var saved point
	var selection charRange
	if !app.followLog {
		send(h, emGetScrollPos, 0, uintptr(unsafe.Pointer(&saved)))
		send(h, emExGetSel, 0, uintptr(unsafe.Pointer(&selection)))
	}
	atEnd := charRange{-1, -1}
	send(h, emExSetSel, 0, uintptr(unsafe.Pointer(&atEnd)))
	send(h, emReplaceSel, 0, ptr(chunk))
	if app.followLog {
		send(h, wmVScroll, sbBottom, 0)
	} else {
		send(h, emExSetSel, 0, uintptr(unsafe.Pointer(&selection)))
		send(h, emSetScrollPos, 0, uintptr(unsafe.Pointer(&saved)))
	}
}

func mainWindow() {
	init := initCommon{Size: uint32(unsafe.Sizeof(initCommon{})), Flags: 0x20}
	pInitCommon.Call(uintptr(unsafe.Pointer(&init)))
	module, _, _ := pGetModule.Call(0)
	name := w("MinecraftToBlenderDesktopV1")
	cursor, _, _ := pLoadCursor.Call(0, 32512)
	largeIcon, smallIcon := appIcons(module)
	ui.brandIcon = largeIcon
	cl := wndClass{Size: uint32(unsafe.Sizeof(wndClass{})), WndProc: syscall.NewCallback(wndProc), Instance: module, Icon: largeIcon, IconSm: smallIcon, Cursor: cursor, Background: colorWindow + 1, ClassName: name}
	if a, _, _ := pRegisterClass.Call(uintptr(unsafe.Pointer(&cl))); a == 0 {
		panic("RegisterClassEx failed")
	}
	screenW, _, _ := pGetSysMetrics.Call(0)
	screenH, _, _ := pGetSysMetrics.Call(1)
	width, height := 1020, 735
	if width > int(screenW)-50 {
		width = int(screenW) - 50
	}
	if height > int(screenH)-95 {
		height = int(screenH) - 95
	}
	if width < 810 {
		width = 810
	}
	if height < 570 {
		height = 570
	}
	x, y := (int(screenW)-width)/2, (int(screenH)-height)/2
	h, _, e := pCreateWindow.Call(0, uintptr(unsafe.Pointer(name)), ptr("Minecraft to Blender v1"), wsOverlappedWindow|wsClipChildren,
		uintptr(x), uintptr(y), uintptr(width), uintptr(height), 0, 0, module, 0)
	if h == 0 {
		panic(fmt.Sprintf("CreateWindowEx failed: %v", e))
	}
	app.main = h
	// Match the app's light interface on supported Windows 10/11 builds.
	dark := int32(0)
	pDwmSetAttribute.Call(h, 20, uintptr(unsafe.Pointer(&dark)), 4)
	createControls()
	pSetTimer.Call(h, 1, 120, 0)
	pShowWindow.Call(h, swShow)
	pUpdateWindow.Call(h)
	var m msg
	for {
		status, _, _ := pGetMessage.Call(uintptr(unsafe.Pointer(&m)), 0, 0, 0)
		if int32(status) <= 0 {
			break
		}
		pTranslate.Call(uintptr(unsafe.Pointer(&m)))
		pDispatch.Call(uintptr(unsafe.Pointer(&m)))
	}
	for _, f := range ui.fonts {
		if f != 0 {
			pDeleteObject.Call(f)
		}
	}
	for _, b := range []uintptr{ui.brushBg, ui.brushCard, ui.brushInput, ui.brushSide, ui.brushLog} {
		if b != 0 {
			pDeleteObject.Call(b)
		}
	}
}
