//go:build windows

package main

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"syscall"
	"unsafe"
)

const previewClass = "MinecraftToBlenderRegionPreview"

var regionPreview struct {
	window, bitmap, token uintptr
	imagePath string
	worldPath string
	minX, minZ, size int
	hoverX, hoverZ int
	hovered bool
}
var regionPreviewCallback uintptr
var regionPreviewRegistered bool

func runPreview(ctx context.Context, world localWorld, workspace, dimension string, useWorldPacks bool, size, x, z int) result {
	if err := ctx.Err(); err != nil {
		return result{what:"Region preview",err:err}
	}
	if !validWorldDir(world.path,world.edition) {
		return result{what:"Region preview",err:fmt.Errorf("Minecraft world is no longer available")}
	}
	if pathsOverlap(world.path, toolsDir(workspace)) {
		return result{what:"Region preview",err:fmt.Errorf("the converter workspace conflicts with the selected Minecraft save. Choose a workspace outside the world folder")}
	}

	work := filepath.Join(workspace,"AppTools","MiEx_Work")
	outDir := filepath.Join(work,"previews")
	if err := os.MkdirAll(outDir,0755); err != nil {
		return result{what:"Region preview",err:err}
	}
	cacheDir := filepath.Join(outDir,"cache")
	fingerprint, fingerprintErr := previewWorldFingerprint(ctx,world.path)
	cacheKey := ""
	if fingerprintErr == nil {
		cacheKey = previewCacheKey(world.path,string(world.edition),dimension,useWorldPacks,size,x,z,appVersion(),fingerprint)
		if cached,ok := cachedPreview(filepath.Join(cacheDir,cacheKey+".png"),outDir);ok {
			if err := ctx.Err(); err != nil {
				_ = os.Remove(cached)
				return result{what:"Region preview",err:err}
			}
			guiLog("Preview cache: world files, coordinates and settings unchanged; reused the saved image without running MiEx.")
			return result{what:"Region preview",output:cached,sourceWorld:world.path,minX:x-size/2,minZ:z-size/2,size:size}
		}
	} else if err := ctx.Err(); err != nil {
		return result{what:"Region preview",err:err}
	} else {
		guiLog("Preview cache unavailable for this world; generating a fresh image: "+fingerprintErr.Error())
	}

	tools,err:=toolsSetup(workspace)
	if err!=nil {return result{what:"Region preview",err:err}}
	logFile:=filepath.Join(workspace,"Minecraft_Blender_Preview.log")
	args:=[]string{"-NoProfile","-NonInteractive","-ExecutionPolicy","Bypass","-File",filepath.Join(tools,"Export_World.ps1"),
		"-WorldPath",world.path,"-Edition",string(world.edition),"-Dimension",dimension,"-PreviewOnly",
		"-Size",strconv.Itoa(size),"-CenterX",strconv.Itoa(x),"-CenterZ",strconv.Itoa(z)}
	if useWorldPacks {
		args=append(args,"-UseWorldResourcePacks")
	}
	if err:=runProcess(ctx,"powershell.exe",args,logFile);err!=nil {
		return result{what:"Region preview",err:fmt.Errorf("MiEx preview failed: %w; see %s",err,logFile),logFile:logFile}
	}
	if err := ctx.Err(); err != nil {
		return result{what:"Region preview",err:err,logFile:logFile}
	}
	imageFile, err := os.CreateTemp(outDir, "Preview_*.png")
	if err != nil {return result{what:"Region preview",err:err,logFile:logFile}}
	output := imageFile.Name()
	if err := imageFile.Close(); err != nil {
		_ = os.Remove(output)
		return result{what:"Region preview",err:err,logFile:logFile}
	}
	loaded,err:=renderSampledPreview(filepath.Join(work,"miex_console.log"),output,x,z,size)
	if err!=nil {
		_ = os.Remove(output)
		return result{what:"Region preview",err:err,logFile:logFile}
	}
	if err := ctx.Err(); err != nil {
		_ = os.Remove(output)
		return result{what:"Region preview",err:err,logFile:logFile}
	}
	// Never cache a snapshot if its source world changed while MiEx was reading.
	if cacheKey != "" {
		endFingerprint, err := previewWorldFingerprint(ctx,world.path)
		if err == nil && endFingerprint == fingerprint {
			if err := storePreviewCache(output,cacheDir,cacheKey); err != nil {
				guiLog("Preview cache could not be saved: "+err.Error())
			}
		} else {
			guiLog("Preview cache skipped because the source world changed during generation or could not be rechecked.")
		}
	}
	guiLog(fmt.Sprintf("Preview ready: %d real chunk images decoded. Small and medium regions use exact X/Z placement; huge regions use coarse color samples. Gray indicates unavailable or unrendered data.",loaded))
	return result{what:"Region preview",output:output,logFile:logFile,sourceWorld:world.path,minX:x-size/2,minZ:z-size/2,size:size}
}

func previewWorldMatches(source string) bool {
	return app.selectedWorld != nil && strings.EqualFold(filepath.Clean(app.selectedWorld.path), filepath.Clean(source))
}

func previewProc(hwnd uintptr, m uint32, wp, lp uintptr) uintptr {
	switch m {
	case wmPaint:
		var ps paintStruct
		dc,_,_:=pBeginPaint.Call(hwnd,uintptr(unsafe.Pointer(&ps)))
		var r rect
		pGetClientRect.Call(hwnd,uintptr(unsafe.Pointer(&r)))
		pFillRect.Call(dc,uintptr(unsafe.Pointer(&r)),ui.brushBg)
		buttonText(dc,"Sampled Minecraft region",rect{32,20,544,46},theme.white,ui.fonts[5],0)
		if regionPreview.bitmap!=0 {
			var gfx uintptr
			if status,_,_:=pGdipCreateGraphics.Call(dc,uintptr(unsafe.Pointer(&gfx)));status==0 && gfx!=0 {
				// Pixel-art maps should keep block edges crisp when enlarged.
				// GDI+ InterpolationModeNearestNeighbor = 5.
				pGdipInterpolation.Call(gfx,5)
				pGdipDrawImage.Call(gfx,regionPreview.bitmap,32,70,512,512)
				pGdipDeleteGraphics.Call(gfx)
			}
		}
		buttonText(dc,"Hover to inspect X/Z. Click to choose after confirmation.",rect{32,592,544,620},theme.muted,ui.fonts[3],0)
		if regionPreview.hovered {
			buttonText(dc,fmt.Sprintf("Hovered coordinates: X=%d   Z=%d",regionPreview.hoverX,regionPreview.hoverZ),rect{32,620,544,646},theme.white,ui.fonts[3],0)
		} else {
			buttonText(dc,"Gray areas indicate unavailable/unrendered chunks.",rect{32,620,544,646},theme.muted,ui.fonts[3],0)
		}
		pEndPaint.Call(hwnd,uintptr(unsafe.Pointer(&ps)))
		return 0
	case wmMouseMove:
		x,y:=int(int16(uint16(lp))),int(int16(uint16(lp>>16)))
		worldX,worldZ,inside:=previewCoordinates(regionPreview.minX,regionPreview.minZ,regionPreview.size,x,y)
		if !regionPreview.hovered || regionPreview.hoverX!=worldX || regionPreview.hoverZ!=worldZ || !inside {
			if inside {
				regionPreview.hoverX,regionPreview.hoverZ=worldX,worldZ
			}
			if regionPreview.hovered!=inside || inside {
				regionPreview.hovered=inside
				pInvalidate.Call(hwnd,0,0)
			}
		}
		ev:=trackMouseEvent{Size:uint32(unsafe.Sizeof(trackMouseEvent{})),Flags:0x2,Window:hwnd}
		pTrackMouseEvent.Call(uintptr(unsafe.Pointer(&ev)))
		return 0
	case wmMouseLeave:
		if regionPreview.hovered {
			regionPreview.hovered=false
			pInvalidate.Call(hwnd,0,0)
		}
		return 0
	case wmLButtonDown:
		if app.busy { return 0 }
		if !previewWorldMatches(regionPreview.worldPath) {
			alert("Preview belongs to another world", "The selected Minecraft world has changed. Generate a new preview for this world.", mbWarn)
			pDestroyWindow.Call(hwnd)
			return 0
		}
		x,y:=int(int16(uint16(lp))),int(int16(uint16(lp>>16)))
		worldX,worldZ,inside:=previewCoordinates(regionPreview.minX,regionPreview.minZ,regionPreview.size,x,y)
		if inside {
			currentX,currentZ:=strings.TrimSpace(getText(idX)),strings.TrimSpace(getText(idZ))
			question:=fmt.Sprintf("Set export center to X=%d, Z=%d?\n\nCurrent export center: X=%s, Z=%s\n\nThis changes the region for the NEXT preview/export. The world itself is unchanged.",worldX,worldZ,currentX,currentZ)
			if alert("Confirm preview coordinates",question,mbWarn|mbYesNo)!=idYes {
				return 0
			}
			setText(app.ctrls[idX],strconv.Itoa(worldX))
			setText(app.ctrls[idZ],strconv.Itoa(worldZ))
			pDestroyWindow.Call(hwnd)
			switchTab(idTabExport)
			state(fmt.Sprintf("Preview center set: X=%d Z=%d. Re-preview to sample this new region.",worldX,worldZ))
		}
		return 0
	case wmKeyDown:
		if wp==vkEscape {pDestroyWindow.Call(hwnd);return 0}
	case wmClose:
		pDestroyWindow.Call(hwnd)
		return 0
	case wmDestroy:
		if regionPreview.bitmap!=0 {pGdipDisposeImage.Call(regionPreview.bitmap)}
		if regionPreview.token!=0 {pGdiplusShutdown.Call(regionPreview.token)}
		if regionPreview.imagePath != "" {
			_ = os.Remove(regionPreview.imagePath)
		}
		regionPreview.window=0
		regionPreview.bitmap=0
		regionPreview.token=0
		regionPreview.imagePath = ""
		regionPreview.worldPath = ""
		regionPreview.hovered = false
		return 0
	}
	r,_,_:=pDefWndProc.Call(hwnd,uintptr(m),wp,lp)
	return r
}

func openPreviewWindow(path string,minX,minZ,size int,worldPath string) {
	if regionPreview.window!=0 {
		pDestroyWindow.Call(regionPreview.window)
	}
	module,_,_:=pGetModule.Call(0)
	name:=w(previewClass)
	if !regionPreviewRegistered {
		regionPreviewCallback=syscall.NewCallback(previewProc)
		cursor,_,_:=pLoadCursor.Call(0,32512)
		large,small:=appIcons(module)
		klass:=wndClass{Size:uint32(unsafe.Sizeof(wndClass{})),WndProc:regionPreviewCallback,Instance:module,Icon:large,IconSm:small,Cursor:cursor,Background:colorWindow+1,ClassName:name}
		if ok,_,_:=pRegisterClass.Call(uintptr(unsafe.Pointer(&klass)));ok==0 {
			_ = os.Remove(path)
			alert("Preview unavailable","Windows could not initialize the region preview window.",mbError)
			return
		}
		regionPreviewRegistered=true
	}
	regionPreview.minX,regionPreview.minZ,regionPreview.size=minX,minZ,size
	regionPreview.hovered=false
	startup:=gdipStartupInput{Version:1}
	if status,_,_:=pGdiplusStartup.Call(uintptr(unsafe.Pointer(&regionPreview.token)),uintptr(unsafe.Pointer(&startup)),0);status!=0 {
		_ = os.Remove(path)
		alert("Preview unavailable","Could not initialize Windows image rendering.",mbError)
		return
	}
	if status,_,_:=pGdipLoadImage.Call(ptr(path),uintptr(unsafe.Pointer(&regionPreview.bitmap)));status!=0 {
		pGdiplusShutdown.Call(regionPreview.token)
		regionPreview.token=0
		_ = os.Remove(path)
		alert("Preview unavailable","Could not open the generated PNG.",mbError)
		return
	}
	w,h:=intSysMetric(0),intSysMetric(1)
	left,top:=max(0,(w-580)/2),max(0,(h-670)/2)
	hwnd,_,_:=pCreateWindow.Call(0,uintptr(unsafe.Pointer(name)),ptr("Minecraft region preview"),uintptr(wsOverlappedWindow|wsVisible),uintptr(left),uintptr(top),580,670,app.main,0,module,0)
	if hwnd==0 {
		pGdipDisposeImage.Call(regionPreview.bitmap)
		pGdiplusShutdown.Call(regionPreview.token)
		regionPreview.bitmap,regionPreview.token=0,0
		_ = os.Remove(path)
		alert("Preview unavailable","Windows could not open the region map.",mbError)
		return
	}
	regionPreview.window=hwnd
	regionPreview.imagePath=path
	regionPreview.worldPath=worldPath
	pShowWindow.Call(hwnd,swShow)
	pInvalidate.Call(hwnd,0,1)
}
