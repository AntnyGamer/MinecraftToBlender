//go:build windows

// Minecraft to Blender: native, portable Win32 UI around the existing MiEx
// exporter and Blender importer. This EXE uses only the Go standard library.
package main

import (
	"bufio"
	"bytes"
	"context"
	"crypto/sha256"
	"embed"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"runtime"
	"sort"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"syscall"
	"time"
	"unicode/utf16"
	"unsafe"
)

//go:embed assets/*
var payload embed.FS

var (
	user32          = syscall.NewLazyDLL("user32.dll")
	kernel32        = syscall.NewLazyDLL("kernel32.dll")
	comdlg32        = syscall.NewLazyDLL("comdlg32.dll")
	shell32         = syscall.NewLazyDLL("shell32.dll")
	comctl32        = syscall.NewLazyDLL("comctl32.dll")
	pRegisterClass  = user32.NewProc("RegisterClassExW")
	pCreateWindow   = user32.NewProc("CreateWindowExW")
	pShowWindow     = user32.NewProc("ShowWindow")
	pUpdateWindow   = user32.NewProc("UpdateWindow")
	pDefWndProc     = user32.NewProc("DefWindowProcW")
	pGetMessage     = user32.NewProc("GetMessageW")
	pTranslate      = user32.NewProc("TranslateMessage")
	pDispatch       = user32.NewProc("DispatchMessageW")
	pPostQuit       = user32.NewProc("PostQuitMessage")
	pSendMessage    = user32.NewProc("SendMessageW")
	pSetWindowText  = user32.NewProc("SetWindowTextW")
	pGetWindowText  = user32.NewProc("GetWindowTextW")
	pGetTextLength  = user32.NewProc("GetWindowTextLengthW")
	pEnableWindow   = user32.NewProc("EnableWindow")
	pSetTimer       = user32.NewProc("SetTimer")
	pKillTimer      = user32.NewProc("KillTimer")
	pMessageBox     = user32.NewProc("MessageBoxW")
	pLoadCursor     = user32.NewProc("LoadCursorW")
	pLoadImage      = user32.NewProc("LoadImageW")
	pGetModule      = kernel32.NewProc("GetModuleHandleW")
	pGetOpenFile    = comdlg32.NewProc("GetOpenFileNameW")
	pBrowseFolder   = shell32.NewProc("SHBrowseForFolderW")
	pGetFolderPath  = shell32.NewProc("SHGetPathFromIDListW")
	pFreeFolder     = kernel32.NewProc("GlobalFree")
	pCoTaskMemFree  = syscall.NewLazyDLL("ole32.dll").NewProc("CoTaskMemFree")
	pInitCommon     = comctl32.NewProc("InitCommonControlsEx")
	pGetStockObject = syscall.NewLazyDLL("gdi32.dll").NewProc("GetStockObject")
	pMoveFileEx     = kernel32.NewProc("MoveFileExW")
)

const (
	wmCreate           = 0x0001
	wmDestroy          = 0x0002
	wmClose            = 0x0010
	wmCommand          = 0x0111
	wmTimer            = 0x0113
	wmSetFont          = 0x0030
	wmSize             = 0x0005
	wmPaint            = 0x000F
	wmEraseBkgnd       = 0x0014
	wmGetMinMaxInfo    = 0x0024
	wmColorStatic      = 0x0138
	wmColorEdit        = 0x0133
	wmColorListbox     = 0x0134
	wmDrawItem         = 0x002B
	wmLogScrollChanged = 0x8000 + 12
	wsOverlappedWindow = 0x00CF0000
	wsVisible          = 0x10000000
	wsChild            = 0x40000000
	wsTabStop          = 0x00010000
	wsBorder           = 0x00800000
	esAutoHScroll      = 0x0080
	esMultiline        = 0x0004
	esReadOnly         = 0x0800
	esAutoVScroll      = 0x0040
	wsVScroll          = 0x00200000
	bsPushbutton       = 0
	bsGroupbox         = 0x00000007
	swShow             = 5
	mbOK               = 0
	mbWarn             = 0x30
	mbError            = 0x10
	mbYesNo            = 0x04
	idYes              = 6
	colorWindow        = 5
	defaultGuiFont     = 17
	pbsMarquee         = 0x08
	pbmSetMarquee      = 0x040A
	pbmSetRange32      = 0x0406
	pbmSetPos          = 0x0402
	ofnExplorer        = 0x00080000
	ofnFileMustExist   = 0x00001000
	ofnPathMustExist   = 0x00000800
	idWorld            = 101
	idWorldBrowse      = 102
	idName             = 103
	idSize             = 104
	idX                = 105
	idZ                = 106
	idMinY             = 107
	idMaxY             = 108
	idExport           = 110
	idBoth             = 111
	idUSD              = 112
	idUSDBrowse        = 113
	idBlender          = 114
	idBlenderBrowse    = 115
	idImport           = 116
	idWorkspace        = 117
	idWorkspaceBrowse  = 118
	idCancel           = 119
	idFolder           = 120
	idBlendOpen        = 121
	idLog              = 122
	idStatus           = 123
	idProgress         = 124
	idTabExport        = 130
	idTabImport        = 131
	idTabSettings      = 132
	idFollow           = 133
	idSelectBedrock    = 134
	idSelectJava       = 135
	idWorldPacks       = 136
	idAutoOpenBlender = 137
)

type wndClass struct {
	Size       uint32
	Style      uint32
	WndProc    uintptr
	ClsExtra   int32
	WndExtra   int32
	Instance   uintptr
	Icon       uintptr
	Cursor     uintptr
	Background uintptr
	MenuName   *uint16
	ClassName  *uint16
	IconSm     uintptr
}
type msg struct {
	HWnd    uintptr
	Message uint32
	WParam  uintptr
	LParam  uintptr
	Time    uint32
	Pt      struct{ X, Y int32 }
	Private uint32
}
type openFilename struct {
	Size            uint32
	Owner           uintptr
	Instance        uintptr
	Filter          *uint16
	CustomFilter    *uint16
	MaxCustomFilter uint32
	FilterIndex     uint32
	File            *uint16
	MaxFile         uint32
	FileTitle       *uint16
	MaxFileTitle    uint32
	InitialDir      *uint16
	Title           *uint16
	Flags           uint32
	FileOffset      uint16
	FileExtension   uint16
	DefExt          *uint16
	CustData        uintptr
	Hook            uintptr
	TemplateName    *uint16
	Reserved        uintptr
	Reserved2       uint32
	FlagsEx         uint32
}
type browseInfo struct {
	Owner       uintptr
	Root        uintptr
	DisplayName *uint16
	Title       *uint16
	Flags       uint32
	Callback    uintptr
	LParam      uintptr
	Image       int32
}
type initCommon struct {
	Size  uint32
	Flags uint32
}

type result struct {
	what    string
	output  string
	err     error
	logFile string
}
type appState struct {
	main          uintptr
	ctrls         map[int]uintptr
	busy          bool
	cancel        context.CancelFunc
	processPID    int
	logCh         chan string
	doneCh        chan result
	logLines      []string
	lastBlend     string
	lastFolder    string
	lastLog       string
	selectedWorld *localWorld
	logShown      int
	followLog     bool
	useWorldPacks bool
	autoOpenBlender bool
}

var app = appState{ctrls: map[int]uintptr{}, logCh: make(chan string, 4096), doneCh: make(chan result, 8)}
var droppedLogLines atomic.Uint64

func w(s string) *uint16   { return syscall.StringToUTF16Ptr(s) }
func ptr(s string) uintptr { return uintptr(unsafe.Pointer(w(s))) }
func send(h uintptr, message uint32, a, b uintptr) uintptr {
	r, _, _ := pSendMessage.Call(h, uintptr(message), a, b)
	return r
}
func setText(h uintptr, s string) { pSetWindowText.Call(h, ptr(s)) }
func getText(id int) string {
	h := app.ctrls[id]
	if h == 0 {
		return ""
	}
	length, _, _ := pGetTextLength.Call(h)
	if length == 0 {
		return ""
	}
	// Read exactly the space needed, avoiding 64 KB allocations for each button.
	b := make([]uint16, int(length)+1)
	n, _, _ := pGetWindowText.Call(h, uintptr(unsafe.Pointer(&b[0])), uintptr(len(b)))
	return syscall.UTF16ToString(b[:n])
}
func enabled(id int, b bool) {
	n := uintptr(0)
	if b {
		n = 1
	}
	pEnableWindow.Call(app.ctrls[id], n)
}
func alert(title, body string, flags uintptr) uintptr {
	r, _, _ := pMessageBox.Call(app.main, ptr(body), ptr(title), flags)
	return r
}
func create(cls, txt string, style uint32, x, y, width, height, id int) uintptr {
	h, _, _ := pCreateWindow.Call(0, ptr(cls), ptr(txt), uintptr(style|wsChild|wsVisible), uintptr(x), uintptr(y), uintptr(width), uintptr(height), app.main, uintptr(id), 0, 0)
	font, _, _ := pGetStockObject.Call(defaultGuiFont)
	send(h, wmSetFont, font, 1)
	if id != 0 {
		app.ctrls[id] = h
	}
	return h
}
func label(txt string, x, y, ww, hh int) { create("STATIC", txt, 0, x, y, ww, hh, 0) }
func field(txt string, x, y, ww, id int) {
	create("EDIT", txt, wsBorder|wsTabStop|esAutoHScroll, x, y, ww, 25, id)
}
func button(txt string, x, y, ww, id int) {
	create("BUTTON", txt, wsTabStop|bsPushbutton, x, y, ww, 29, id)
}
func group(txt string, x, y, ww, hh int) { create("BUTTON", txt, bsGroupbox, x, y, ww, hh, 0) }

func defaultWorkspace() string {
	base := os.Getenv("LOCALAPPDATA")
	if base == "" {
		base = os.Getenv("USERPROFILE")
	}
	if base == "" {
		base = "."
	}
	return filepath.Join(base, "MinecraftToBlender")
}
func autoOpenPreferencePath() string {
	return filepath.Join(defaultWorkspace(), "preferences.json")
}

func loadAutoOpenBlender() bool {
	data, err := os.ReadFile(autoOpenPreferencePath())
	if err != nil {
		return true
	}
	var saved struct {
		AutoOpenBlender *bool `json:"autoOpenBlender"`
	}
	if json.Unmarshal(data, &saved) != nil || saved.AutoOpenBlender == nil {
		return true
	}
	return *saved.AutoOpenBlender
}

func saveAutoOpenBlender(value bool) error {
	path := autoOpenPreferencePath()
	if err := os.MkdirAll(filepath.Dir(path), 0755); err != nil {
		return err
	}
	data, err := json.Marshal(struct {
		AutoOpenBlender bool `json:"autoOpenBlender"`
	}{value})
	if err != nil {
		return err
	}
	temp := path + ".new"
	if err := os.WriteFile(temp, append(data, '\n'), 0644); err != nil {
		return err
	}
	if ok, _, moveErr := pMoveFileEx.Call(ptr(temp), ptr(path), 0x1|0x8); ok == 0 {
		_ = os.Remove(temp)
		return fmt.Errorf("cannot save Blender auto-open preference: %w", moveErr)
	}
	return nil
}

func detectBlender() string {
	if path, e := exec.LookPath("blender.exe"); e == nil {
		return path
	}
	roots := []string{os.Getenv("ProgramFiles"), os.Getenv("ProgramW6432")}
	var found []string
	for _, root := range roots {
		if root == "" {
			continue
		}
		p := filepath.Join(root, "Blender Foundation", "Blender *", "blender.exe")
		hits, _ := filepath.Glob(p)
		found = append(found, hits...)
	}
	sort.Sort(sort.Reverse(sort.StringSlice(found)))
	if len(found) > 0 {
		return found[0]
	}
	return ""
}

func selectFile(filter, title string) string {
	b := make([]uint16, 16384)
	f := strings.ReplaceAll(filter, "|", "\x00") + "\x00\x00"
	fbuf := utf16.Encode([]rune(f))
	flags := uint32(ofnExplorer | ofnFileMustExist | ofnPathMustExist)
	dialog := openFilename{Size: uint32(unsafe.Sizeof(openFilename{})), Owner: app.main, Filter: &fbuf[0], File: &b[0], MaxFile: uint32(len(b)), Title: w(title), Flags: flags}
	ret, _, _ := pGetOpenFile.Call(uintptr(unsafe.Pointer(&dialog)))
	if ret == 0 {
		return ""
	}
	return syscall.UTF16ToString(b)
}
func selectFolder() string { return selectFolderTitle("Choose the workspace folder") }
func selectFolderTitle(title string) string {
	b := make([]uint16, 260)
	info := browseInfo{Owner: app.main, DisplayName: &b[0], Title: w(title), Flags: 0x40 | 0x01} // BIF_NEWDIALOGSTYLE | RETURNONLYFSDIRS
	pid, _, _ := pBrowseFolder.Call(uintptr(unsafe.Pointer(&info)))
	if pid == 0 {
		return ""
	}
	defer pCoTaskMemFree.Call(pid)
	dst := make([]uint16, 32768)
	ok, _, _ := pGetFolderPath.Call(pid, uintptr(unsafe.Pointer(&dst[0])))
	if ok == 0 {
		return ""
	}
	return syscall.UTF16ToString(dst)
}
func trimErr(err error) string {
	if err == nil {
		return ""
	}
	return err.Error()
}
func validateName(v string) bool {
	if !regexp.MustCompile(`^[A-Za-z][A-Za-z0-9_]{0,60}$`).MatchString(v) {
		return false
	}
	// Windows reserves device names even when they look like ordinary folder names.
	upper := strings.ToUpper(v)
	if upper == "CON" || upper == "PRN" || upper == "AUX" || upper == "NUL" {
		return false
	}
	if len(upper) == 4 && (strings.HasPrefix(upper, "COM") || strings.HasPrefix(upper, "LPT")) {
		return upper[3] < '1' || upper[3] > '9'
	}
	return true
}
func intField(id int, min, max int) (int, error) {
	s := strings.TrimSpace(getText(id))
	n, e := strconv.Atoi(s)
	if e != nil || n < min || n > max {
		return 0, fmt.Errorf("invalid number: %s (must be %d to %d)", s, min, max)
	}
	return n, nil
}
func guiLog(line string) {
	select {
	case app.logCh <- line:
	default:
		droppedLogLines.Add(1)
	}
}
func appendLog(s string) {
	if strings.TrimSpace(s) == "" {
		return
	}
	// Only the first 4000 bytes are shown; don't lowercase huge MiEx JSON
	// responses solely to detect short, human-readable progress messages.
	if len(s) > 4000 {
		s = s[:4000] + "..."
	}
	// Log-based stages are real milestones, not guessed completion percentages.
	if app.busy {
		lower := strings.ToLower(s)
		switch {
		case strings.Contains(lower, "copying a safe, read-only snapshot"):
			state("Preparing a snapshot of your selected Minecraft world...")
		case strings.Contains(lower, "snapshot ready"):
			state("World prepared. Loading MiEx export resources...")
		case strings.Contains(lower, "verified bedrock world directory"):
			state("World unpacked. Preparing export resources...")
		case strings.Contains(lower, "extracting base_resource_pack"):
			state("Preparing Minecraft textures and models...")
		case strings.Contains(lower, "starting full-detail export"):
			state("MiEx is converting Minecraft blocks into USD...")
		case strings.Contains(lower, "world exported successfully"):
			state("USD export finished. Checking files...")
		case strings.Contains(lower, "checking terrain and importing"):
			state("Checking terrain and starting Blender import...")
		case strings.Contains(lower, "usd variant: render"):
			state("Checking render geometry for actual terrain...")
		case strings.Contains(lower, "usd variant: proxy"):
			state("Checking proxy geometry for actual terrain...")
		case strings.Contains(lower, "phase: importing with miex"):
			state("Building Blender meshes and Minecraft materials...")
		case strings.Contains(lower, "phase: saving"):
			state("Saving the Blender project...")
		case strings.Contains(lower, "output .blend saved"):
			state("Blender project saved. Checking final output...")
		}
	}
	app.logLines = append(app.logLines, s)
	if len(app.logLines) > 10000 {
		app.logLines = app.logLines[len(app.logLines)-8000:]
		app.logShown = -1
	}
}
func state(txt string) { setText(app.ctrls[idStatus], txt) }
func setBusy(b bool) {
	app.busy = b
	if b {
		ui.progressComplete = false
		ui.progressFrame = 0
	}
	pInvalidate.Call(app.main, 0, 0)
	for _, id := range []int{idSelectBedrock, idSelectJava, idWorldBrowse, idWorld, idName, idSize, idX, idZ, idMinY, idMaxY, idExport, idBoth, idUSD, idUSDBrowse, idBlender, idBlenderBrowse, idImport, idWorkspace, idWorkspaceBrowse, idWorldPacks, idAutoOpenBlender} {
		enabled(id, !b)
	}
	enabled(idCancel, b)
	enabled(idBlendOpen, !b && app.lastBlend != "")
	show(idCancel, b)
	show(idBlendOpen, !b && app.lastBlend != "")
	refreshButtons()
	n := uintptr(0)
	if b {
		n = 1
	}
	send(app.ctrls[idProgress], pbmSetMarquee, n, 65)
}
func toolsDir(workspace string) string { return filepath.Join(workspace, "AppTools") }
func outputUSD(workspace, name string) string {
	return filepath.Join(toolsDir(workspace), "MiEx_Work", "exports", name, name+".usd")
}
func toolsSetup(workspace string) (string, error) {
	base := toolsDir(workspace)
	if err := os.MkdirAll(base, 0755); err != nil {
		return "", err
	}
	paths, err := payload.ReadDir("assets")
	if err != nil {
		return "", err
	}
	for _, entry := range paths {
		if entry.IsDir() {
			continue
		}
		raw, err := payload.ReadFile("assets/" + entry.Name())
		if err != nil {
			return "", err
		}
		dest := filepath.Join(base, entry.Name())
		// Preserve unchanged files and timestamps across repeated runs.
		if old, readErr := os.ReadFile(dest); readErr == nil && bytes.Equal(old, raw) {
			continue
		}
		temp := dest + ".new"
		if err = os.WriteFile(temp, raw, 0644); err != nil {
			return "", err
		}
		// Replace atomically on the same volume. Never delete the previous
		// helper if Windows rejects the replacement (e.g. it is in use).
		if ok, _, moveErr := pMoveFileEx.Call(ptr(temp), ptr(dest), 0x1|0x8); ok == 0 {
			_ = os.Remove(temp)
			return "", fmt.Errorf("cannot update %s: %w", entry.Name(), moveErr)
		}
	}
	return base, nil
}
func usdFiles(src string) error {
	if strings.ToLower(filepath.Ext(src)) != ".usd" {
		return errors.New("choose the main .usd export file")
	}
	info, e := os.Stat(src)
	if e != nil {
		return fmt.Errorf("USD not found: %w", e)
	}
	if info.IsDir() || info.Size() == 0 {
		return errors.New("main USD is an empty file or a folder")
	}
	dir := filepath.Dir(src)
	name := strings.TrimSuffix(filepath.Base(src), filepath.Ext(src))
	materialsPath := filepath.Join(dir, name+"_materials.json")
	materialInfo, err := os.Stat(materialsPath)
	if err != nil || materialInfo.IsDir() || materialInfo.Size() == 0 {
		return fmt.Errorf("missing or empty %s", filepath.Base(materialsPath))
	}
	// A present but truncated JSON file previously passed validation.
	f, err := os.Open(materialsPath)
	if err != nil {
		return err
	}
	var materials map[string]json.RawMessage
	decoder := json.NewDecoder(f)
	decodeErr := decoder.Decode(&materials)
	if decodeErr == nil {
		var extra json.RawMessage
		if trailing := decoder.Decode(&extra); trailing != io.EOF {
			decodeErr = fmt.Errorf("unexpected trailing JSON: %v", trailing)
		}
	}
	f.Close()
	if decodeErr != nil || materials == nil {
		return fmt.Errorf("MiEx materials JSON is not valid: %v", decodeErr)
	}
	chunkDir := filepath.Join(dir, name+"_chunks")
	chunkInfo, err := os.Stat(chunkDir)
	if err != nil || !chunkInfo.IsDir() {
		return fmt.Errorf("missing chunk folder: %s", chunkDir)
	}
	chunkFolder, err := os.Open(chunkDir)
	if err != nil {
		return err
	}
	defer chunkFolder.Close()
	// Read directory entries in bounded batches. Large exports can contain
	// thousands of USD layers; loading and sorting every name is unnecessary
	// when validation only needs one non-empty layer.
	for {
		entries, readErr := chunkFolder.ReadDir(128)
		if readErr != nil && readErr != io.EOF {
			return readErr
		}
		for _, entry := range entries {
			if entry.IsDir() || !strings.HasSuffix(strings.ToLower(entry.Name()), ".usd") {
				continue
			}
			if chunk, infoErr := entry.Info(); infoErr == nil && chunk.Size() > 0 {
				return nil
			}
		}
		if readErr == io.EOF {
			break
		}
	}
	return errors.New("chunk folder contains no non-empty USD layer files")
}

// Use only the pinned official MiEx importer in the application-managed tools
// folder. Executing a similarly named Python file next to an imported USD is
// unsafe: USD archives may come from other people or untrusted directories.
const officialMiExImporterSHA256 = "68b9736a7eecf061cb052e357b9e5f0ff55ae48792f523dd932f2a6275c7412c"
const officialMiExImporterURL = "https://raw.githubusercontent.com/BramStoutProductions/MiEx/631e9fc2fde8c749bf59d4c3495492e62a83ef6c/extras/Blender/BlenderAddon/MiExImport.py"

func officialMiExImporter(ctx context.Context, tools string) (string, error) {
	path := filepath.Join(tools, "MiExImport.py")
	if existing, err := os.ReadFile(path); err == nil {
		if fmt.Sprintf("%x", sha256.Sum256(existing)) == officialMiExImporterSHA256 {
			return path, nil
		}
		guiLog("Local MiEx importer differs from the pinned upstream version; downloading a verified replacement.")
	}
	req, err := http.NewRequestWithContext(ctx, "GET", officialMiExImporterURL, nil)
	if err != nil {
		return "", err
	}
	client := &http.Client{Timeout: 35 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		return "", fmt.Errorf("cannot download official MiEx importer: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return "", fmt.Errorf("cannot download official MiEx importer: HTTP %d", resp.StatusCode)
	}
	data, err := io.ReadAll(io.LimitReader(resp.Body, 1024*1024+1))
	if err != nil {
		return "", err
	}
	if len(data) > 1024*1024 || fmt.Sprintf("%x", sha256.Sum256(data)) != officialMiExImporterSHA256 {
		return "", errors.New("official MiEx importer does not match the pinned SHA256; refusing to run it")
	}
	temp := path + ".new"
	if err := os.WriteFile(temp, data, 0644); err != nil {
		return "", err
	}
	if ok, _, moveErr := pMoveFileEx.Call(ptr(temp), ptr(path), 0x1|0x8); ok == 0 {
		_ = os.Remove(temp)
		return "", fmt.Errorf("cannot install verified MiEx importer: %w", moveErr)
	}
	return path, nil
}

func runProcess(ctx context.Context, name string, args []string, logfile string) error {
	if err := os.MkdirAll(filepath.Dir(logfile), 0755); err != nil {
		return err
	}
	f, err := os.Create(logfile)
	if err != nil {
		return err
	}
	defer f.Close()
	cmd := exec.Command(name, args...)
	cmd.SysProcAttr = &syscall.SysProcAttr{HideWindow: true}
	// One shared pipe preserves combined diagnostic information without blocking on stderr.
	r, wpipe := io.Pipe()
	cmd.Stdout = wpipe
	cmd.Stderr = wpipe
	if err = cmd.Start(); err != nil {
		wpipe.Close()
		r.Close()
		return err
	}
	appPID := cmd.Process.Pid
	guiLog("Running: " + filepath.Base(name))
	var wg sync.WaitGroup
	readErrors := make(chan error, 1)
	wg.Add(1)
	go func() {
		defer wg.Done()
		scanner := bufio.NewScanner(r)
		scanner.Buffer(make([]byte, 65536), 8*1024*1024)
		// Batch disk writes on verbose exports, without buffering the full log.
		logWriter := bufio.NewWriterSize(f, 256*1024)
		var writeErr error
		for scanner.Scan() {
			line := scanner.Text()
			if writeErr == nil {
				if _, writeErr = logWriter.WriteString(line); writeErr == nil {
					writeErr = logWriter.WriteByte('\n')
				}
			}
			guiLog(line)
		}
		if err := logWriter.Flush(); writeErr == nil {
			writeErr = err
		}
		readErr := scanner.Err()
		if readErr != nil {
			// Stop the pipe writer too, so an oversized line cannot leave the
			// child blocked forever while the parent waits for it to exit.
			_ = r.CloseWithError(readErr)
		} else {
			readErr = writeErr
		}
		if readErr != nil {
			guiLog("Process log read error: " + readErr.Error())
			readErrors <- readErr
		}
	}()
	done := make(chan error, 1)
	go func() { done <- cmd.Wait(); wpipe.Close() }()
	select {
	case err = <-done:
	case <-ctx.Done():
		// PowerShell starts a Java subprocess. Terminate the process tree, not only its parent.
		killCtx, stopKill := context.WithTimeout(context.Background(), 8*time.Second)
		killErr := exec.CommandContext(killCtx, "taskkill.exe", "/T", "/F", "/PID", strconv.Itoa(appPID)).Run()
		stopKill()
		if killErr != nil {
			// Fall back to killing the parent when taskkill is unavailable.
			_ = cmd.Process.Kill()
			guiLog("Cancel warning: Windows could not terminate the complete process tree. Check Task Manager for remaining Java or Blender processes.")
		}
		err = <-done
		if err == nil {
			err = ctx.Err()
		}
	}
	wg.Wait()
	r.Close()
	if ctx.Err() != nil {
		return ctx.Err()
	}
	select {
	case readErr := <-readErrors:
		return fmt.Errorf("cannot read complete process output: %w", readErr)
	default:
	}
	return err
}
// blenderOutputPath keeps existing Blender projects intact when importing again.
func blenderOutputPath(src string) (string, error) {
	base := strings.TrimSuffix(src, filepath.Ext(src))
	for i := 1; i <= 100; i++ {
		path := base + ".blend"
		if i > 1 {
			path = fmt.Sprintf("%s_%d.blend", base, i)
		}
		if _, err := os.Stat(path); os.IsNotExist(err) {
			return path, nil
		} else if err != nil {
			return "", fmt.Errorf("cannot inspect Blender output %s: %w", path, err)
		}
	}
	return "", errors.New("all 100 Blender output names are in use; move or rename older files")
}

func doImport(ctx context.Context, src, blender, tools string) (string, error) {
	if err := usdFiles(src); err != nil {
		return "", err
	}
	return doImportValidated(ctx, src, blender, tools)
}

// An export is already checked by runExport. Avoid parsing its large material
// manifest and enumerating its USD chunk directory a second time.
func doImportValidated(ctx context.Context, src, blender, tools string) (string, error) {
	if blender == "" {
		return "", errors.New("Blender was not detected. Select blender.exe in the application.")
	}
	if _, err := os.Stat(blender); err != nil {
		return "", fmt.Errorf("Blender executable not found: %s", blender)
	}
	importer, err := officialMiExImporter(ctx, tools)
	if err != nil {
		return "", err
	}
	target, err := blenderOutputPath(src)
	if err != nil {
		return "", err
	}
	guiLog("Checking terrain and importing Minecraft geometry into Blender...")
	logFile := filepath.Join(filepath.Dir(src), "Minecraft_Blender_Import.log")
	args := []string{"--background", "--factory-startup", "--python", filepath.Join(tools, "Import_Existing_USD.py"), "--", src, importer, target}
	if err := runProcess(ctx, blender, args, logFile); err != nil {
		return "", fmt.Errorf("Blender import failed: %w; details: %s", err, logFile)
	}
	out, err := os.Stat(target)
	if err != nil || out.Size() == 0 {
		return "", fmt.Errorf("Blender did not save a complete .blend. Check %s", logFile)
	}
	confirmed, err := confirmedBlenderImport(logFile)
	if err != nil {
		return "", fmt.Errorf("cannot validate Blender import log %s: %w", logFile, err)
	}
	if !confirmed {
		return "", fmt.Errorf("Blender did not confirm a complete import; see %s", logFile)
	}
	guiLog("Blender file created: " + target)
	guiLog("IMPORTANT: Review the model visually for missing Minecraft blocks and textures.")
	return target, nil
}

// Never place the working files inside a live Minecraft world, nor select a
// world located inside the app's working files. This check must precede writes.
func pathsOverlap(a, b string) bool {
	aa, ea := filepath.Abs(a)
	bb, eb := filepath.Abs(b)
	if ea != nil || eb != nil {
		return true
	}
	aa, bb = strings.ToLower(filepath.Clean(aa)), strings.ToLower(filepath.Clean(bb))
	return aa == bb || strings.HasPrefix(aa, bb+string(filepath.Separator)) || strings.HasPrefix(bb, aa+string(filepath.Separator))
}

func runExport(ctx context.Context, worldPath string, edition worldEdition, workspace, exportName, blender string, size, x, z, minY, maxY int, useWorldPacks, alsoImport bool) result {
	if pathsOverlap(worldPath, toolsDir(workspace)) {
		return result{what: "Export", err: errors.New("the converter workspace conflicts with the selected Minecraft save. Choose a workspace outside the world folder")}
	}
	if !validWorldDir(worldPath, edition) {
		return result{what: "Export", err: fmt.Errorf("source %s world folder is invalid: %s", edition, worldPath)}
	}
	tools, err := toolsSetup(workspace)
	if err != nil {
		return result{what: "Export", err: err}
	}
	guiLog("Preparing MiEx export...")
	args := []string{"-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", filepath.Join(tools, "Export_World.ps1"), "-WorldPath", worldPath, "-Edition", string(edition), "-Size", strconv.Itoa(size), "-CenterX", strconv.Itoa(x), "-CenterZ", strconv.Itoa(z), "-MinY", strconv.Itoa(minY), "-MaxY", strconv.Itoa(maxY), "-ExportName", exportName}
	if useWorldPacks {
		args = append(args, "-UseWorldResourcePacks")
	}
	file := filepath.Join(workspace, "Minecraft_Blender_Export.log")
	err = runProcess(ctx, "powershell.exe", args, file)
	if err != nil {
		return result{what: "Export", err: fmt.Errorf("export failed: %w; see %s", err, file), logFile: file}
	}
	usd := outputUSD(workspace, exportName)
	if err = usdFiles(usd); err != nil {
		return result{what: "Export", err: fmt.Errorf("export process ended, but files are incomplete: %w", err), logFile: file}
	}
	guiLog("Exported world: " + usd)
	if alsoImport {
		target, e := doImportValidated(ctx, usd, blender, tools)
		return result{what: "Export + import", output: target, err: e, logFile: file}
	}
	return result{what: "Export", output: usd, logFile: file}
}
func startExport(both bool) {
	if app.selectedWorld == nil {
		alert("Select a Minecraft world", "Choose Select Bedrock World or Select Java World, then click a world from your library.", mbWarn)
		return
	}
	world := *app.selectedWorld
	if !validWorldDir(world.path, world.edition) {
		alert("World unavailable", "The selected world is no longer present. Choose it again.", mbWarn)
		return
	}
	workspace := strings.TrimSpace(getText(idWorkspace))
	if workspace == "" {
		alert("Workspace required", "Choose a workspace folder.", mbWarn)
		return
	}
	name := strings.TrimSpace(getText(idName))
	if !validateName(name) {
		alert("Invalid export name", "Use letters, digits or underscores (up to 61 characters), start with a letter, and avoid Windows reserved names such as CON or AUX.", mbWarn)
		return
	}
	size, e := intField(idSize, 16, 8192)
	if e != nil || size%16 != 0 {
		alert("Invalid export size", "Size must be a multiple of 16 between 16 and 8192.", mbWarn)
		return
	}
	x, e := intField(idX, -30000000, 30000000)
	if e != nil {
		alert("Invalid X coordinate", trimErr(e), mbWarn)
		return
	}
	z, e := intField(idZ, -30000000, 30000000)
	if e != nil {
		alert("Invalid Z coordinate", trimErr(e), mbWarn)
		return
	}
	minY, e := intField(idMinY, -256, 2048)
	if e != nil {
		alert("Invalid minimum height", trimErr(e), mbWarn)
		return
	}
	maxY, e := intField(idMaxY, -256, 2048)
	if e != nil || minY > maxY {
		alert("Invalid height range", "Min Y cannot be greater than Max Y; both must be -256 through 2048.", mbWarn)
		return
	}
	blender := strings.TrimSpace(getText(idBlender))
	if both && blender == "" {
		alert("Blender required", "Select the installed blender.exe for automatic import.", mbWarn)
		return
	}
	// The underlying MiEx exporter replaces an existing export with the same name.
	if _, err := os.Stat(outputUSD(workspace, name)); err == nil {
		if alert("Existing export", "An export with this name already exists in the workspace and will be replaced. Continue?", mbWarn|mbYesNo) != idYes {
			return
		}
	}
	// Default coordinates remain 0,0, but warn when the selected region does
	// not include the save's recorded player position or spawn location.
	if world.hasCenter && worldCenterOutsideRegion(x, z, size, world.x, world.z) {
		warning := fmt.Sprintf("The selected %d x %d region is centered at X=%d, Z=%d, but this world records a player/spawn location near X=%d, Z=%d outside that area.\n\nThe region might contain no saved terrain. Center X/Z will stay as entered. Continue anyway?", size, size, x, z, world.x, world.z)
		if alert("Region may miss the world", warning, mbWarn|mbYesNo) != idYes {
			return
		}
	}
	// Warn users before a large, potentially long export.
	if size >= 1152 && alert("Large export", "A region this large can take a long time and use significant memory. Continue?", mbWarn|mbYesNo) != idYes {
		return
	}
	ctx, cancel := context.WithCancel(context.Background())
	app.cancel = cancel
	app.lastBlend = "" // A new operation must not expose a previous project on failure.
	resetLog()
	state("Exporting Minecraft world...")
	setBusy(true)
	app.lastFolder = filepath.Join(toolsDir(workspace), "MiEx_Work", "exports", name)
	guiLog(fmt.Sprintf("Exporting %d x %d blocks around X=%d Z=%d", size, size, x, z))
	useWorldPacks := app.useWorldPacks
	go func() {
		app.doneCh <- runExport(ctx, world.path, world.edition, workspace, name, blender, size, x, z, minY, maxY, useWorldPacks, both)
	}()
}
func startImport() {
	usd := strings.Trim(strings.TrimSpace(getText(idUSD)), "\"")
	if usd == "" {
		alert("Select a USD file", "Select the main MiEx .usd (not a chunk USD).", mbWarn)
		return
	}
	workspace := strings.TrimSpace(getText(idWorkspace))
	if workspace == "" {
		alert("Workspace required", "Choose a workspace folder.", mbWarn)
		return
	}
	blender := strings.TrimSpace(getText(idBlender))
	if blender == "" {
		alert("Blender required", "Select the installed blender.exe.", mbWarn)
		return
	}
	if e := usdFiles(usd); e != nil {
		alert("Incomplete USD", e.Error(), mbError)
		return
	}
	ctx, cancel := context.WithCancel(context.Background())
	app.cancel = cancel
	app.lastBlend = "" // Only the current import may populate Open Project.
	resetLog()
	state("Importing existing USD into Blender...")
	setBusy(true)
	app.lastFolder = filepath.Dir(usd)
	go func() {
		tools, e := toolsSetup(workspace)
		if e != nil {
			app.doneCh <- result{what: "Import", err: e}
			return
		}
		out, e := doImport(ctx, usd, blender, tools)
		app.doneCh <- result{what: "Import", output: out, err: e}
	}()
}
func browseButton(id int) {
	switch id {
	case idWorldBrowse:
		openWorldLibrary(bedrockEdition)
	case idUSDBrowse:
		if s := selectFile("Main MiEx USD (*.usd)|*.usd|All files (*.*)|*.*", "Select the main MiEx USD export"); s != "" {
			setText(app.ctrls[idUSD], s)
		}
	case idBlenderBrowse:
		if s := selectFile("Blender (blender.exe)|blender.exe|Executables (*.exe)|*.exe", "Select Blender.exe"); s != "" {
			setText(app.ctrls[idBlender], s)
		}
	case idWorkspaceBrowse:
		if s := selectFolder(); s != "" {
			setText(app.ctrls[idWorkspace], s)
		}
	}
}
func openFolder(path string) {
	if path == "" {
		path = strings.TrimSpace(getText(idWorkspace))
	}
	if path == "" {
		return
	}
	// Browse the nearest existing directory; don't manufacture a missing
	// export folder after a failed or cancelled operation.
	for {
		if info, err := os.Stat(path); err == nil && info.IsDir() {
			break
		}
		parent := filepath.Dir(path)
		if parent == path {
			alert("Folder unavailable", "No accessible output folder could be found.", mbError)
			return
		}
		path = parent
	}
	cmd := exec.Command("explorer.exe", path)
	if err := cmd.Start(); err != nil {
		alert("Cannot open output folder", err.Error(), mbError)
	} else {
		_ = cmd.Process.Release()
	}
}
const createNoWindow = 0x08000000 // Windows CREATE_NO_WINDOW

func blenderProjectCommand(blender, path string) *exec.Cmd {
	cmd := exec.Command(blender, path)
	// Blender's console must stay hidden without hiding its main GUI window.
	cmd.SysProcAttr = &syscall.SysProcAttr{CreationFlags: createNoWindow}
	return cmd
}

func openBlenderProject(blender, path string) error {
	if blender == "" {
		return errors.New("Select blender.exe in the Import USD tab")
	}
	if _, err := os.Stat(path); err != nil {
		return fmt.Errorf("Blender project unavailable: %w", err)
	}
	cmd := blenderProjectCommand(blender, path)
	if err := cmd.Start(); err != nil {
		return err
	}
	_ = cmd.Process.Release()
	return nil
}

func onCompleted(r result) {
	setBusy(false)
	app.cancel = nil
	if r.err != nil {
		ui.progressComplete = false
		app.lastLog = r.logFile
		state("Failed — see details in log")
		appendLog("ERROR: " + r.err.Error())
		updateLog()
		alert(r.what+" failed", r.err.Error(), mbError)
		return
	}
	ui.progressComplete = true
	app.lastFolder = filepath.Dir(r.output)
	if strings.HasSuffix(strings.ToLower(r.output), ".blend") {
		app.lastBlend = r.output
		layoutUI()
		enabled(idBlendOpen, true)
		state("Blender project saved — open and inspect the scene")
		if app.autoOpenBlender {
			if err := openBlenderProject(getText(idBlender), r.output); err != nil {
				state("Blender project saved — automatic open failed")
				appendLog("WARNING: Could not automatically open Blender: " + err.Error())
			} else {
				state("Blender project saved and opened")
				appendLog("Opened in Blender: " + r.output)
			}
		}
	} else {
		// A USD-only export has no matching new Blender project. Do not leave
		// Open project pointing to a previous conversion.
		app.lastBlend = ""
		layoutUI()
		enabled(idBlendOpen, false)
		setText(app.ctrls[idUSD], r.output)
		state("USD exported — import it in Step 2")
	}
	appendLog("SUCCESS: " + r.output)
	updateLog()
}
func tick() {
	if app.busy {
		ui.progressFrame++
		a := ui.activityTop + 76
		area := rect{Left: 227, Top: int32(a - 1), Right: int32(ui.w - 25), Bottom: int32(a + 8)}
		pInvalidate.Call(app.main, uintptr(unsafe.Pointer(&area)), 0)
	}
	changed := false
	for i := 0; i < 180; i++ {
		select {
		case line := <-app.logCh:
			appendLog(line)
			changed = true
		default:
			i = 180
		}
	}
	if dropped := droppedLogLines.Swap(0); dropped > 0 {
		appendLog(fmt.Sprintf("WARNING: %d console messages were skipped because output arrived too quickly. The full process log is preserved on disk.", dropped))
		changed = true
	}
	if changed {
		updateLog()
	}
	select {
	case r := <-app.doneCh:
		onCompleted(r)
	default:
	}
}
func wndProc(h uintptr, m uint32, wp, lp uintptr) uintptr {
	switch m {
	case wmCreate:
		return 0
	case wmSize:
		layoutUI()
		return 0
	case wmPaint:
		paintMain(h)
		return 0
	case wmEraseBkgnd:
		return 1
	case wmColorStatic, wmColorEdit, wmColorListbox:
		return colorControl(m, wp, lp)
	case wmDrawItem:
		return paintButton(lp)
	case wmGetMinMaxInfo:
		setMinimumSize(lp)
		return 0
	case wmLogScrollChanged:
		updateFollowFromScroll()
		return 0
	case wmCommand:
		id := int(wp & 0xffff)
		if app.busy && id != idCancel && id != idTabExport && id != idTabImport && id != idTabSettings && id != idFollow && id != idFolder && id != idBlendOpen {
			return 0
		}
		switch id {
		case idSelectBedrock:
			openWorldLibrary(bedrockEdition)
		case idSelectJava:
			openWorldLibrary(javaEdition)
		case idTabExport, idTabImport, idTabSettings:
			switchTab(id)
		case idFollow:
			resumeFollowing()
		case idWorldPacks:
			app.useWorldPacks = !app.useWorldPacks
			if app.useWorldPacks {
				setText(app.ctrls[idWorldPacks], "Use world resource packs: On")
			} else {
				setText(app.ctrls[idWorldPacks], "Use world resource packs: Off")
			}
			refreshButtons()
		case idAutoOpenBlender:
			next := !app.autoOpenBlender
			if err := saveAutoOpenBlender(next); err != nil {
				alert("Cannot save preference", err.Error(), mbError)
			} else {
				app.autoOpenBlender = next
				setText(app.ctrls[idAutoOpenBlender], autoOpenBlenderLabel())
				refreshButtons()
			}
		case idWorldBrowse, idUSDBrowse, idBlenderBrowse, idWorkspaceBrowse:
			browseButton(id)
		case idExport:
			startExport(false)
		case idBoth:
			startExport(true)
		case idImport:
			startImport()
		case idCancel:
			if app.cancel != nil {
				state("Cancelling process...")
				app.cancel()
				app.cancel = nil
			}
		case idFolder:
			openFolder(app.lastFolder)
		case idBlendOpen:
			if app.lastBlend != "" {
				if err := openBlenderProject(getText(idBlender), app.lastBlend); err != nil {
					alert("Could not open Blender", err.Error(), mbError)
				}
			}
		}
		return 0
	case wmTimer:
		tick()
		return 0
	case wmClose:
		if app.busy {
			alert("Import/export running", "Click Cancel operation before closing, to stop the child processes safely.", mbWarn)
			return 0
		}
		// default close behavior
	case wmDestroy:
		releaseSelectedImage()
		pKillTimer.Call(h, 1)
		pPostQuit.Call(0)
		return 0
	}
	r, _, _ := pDefWndProc.Call(h, uintptr(m), wp, lp)
	return r
}
// appIcons selects the closest embedded Windows icon for each system size.
func appIcons(module uintptr) (uintptr, uintptr) {
	resource := w("APP")
	load := func(width, height uintptr) uintptr {
		icon, _, _ := pLoadImage.Call(module, uintptr(unsafe.Pointer(resource)), 1, width, height, 0x8000)
		return icon
	}
	largeW, _, _ := pGetSysMetrics.Call(11) // SM_CXICON
	largeH, _, _ := pGetSysMetrics.Call(12) // SM_CYICON
	smallW, _, _ := pGetSysMetrics.Call(49) // SM_CXSMICON
	smallH, _, _ := pGetSysMetrics.Call(50) // SM_CYSMICON
	return load(largeW, largeH), load(smallW, smallH)
}

func main() {
	app.autoOpenBlender = loadAutoOpenBlender()
	runtime.LockOSThread()
	mainWindow()
}
