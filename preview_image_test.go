package main

import (
	"encoding/base64"
	"fmt"
	"image/png"
	"os"
	"path/filepath"
	"testing"
)

func TestSampledPreviewUsesActualChunkColors(t *testing.T) {
	dir := t.TempDir()
	logPath := filepath.Join(dir, "miex.log")
	output := filepath.Join(dir, "preview.png")
	// MiEx serializes ARGB int pixels as little-endian BGRA bytes.
	pixels := make([]byte, 16*16*4)
	for i:=0;i<len(pixels);i+=4 {
		pixels[i+0]=0x12
		pixels[i+1]=0x34
		pixels[i+2]=0x56
		pixels[i+3]=0xff
	}
	// The second source row is distinct; the PNG must scale it rather than
	// repeat the first source row's whole chunk.
	pixels[16*4+2] = 0x9a
	// Unrendered and semi-transparent colors must not turn into opaque black.
	pixels[7] = 0
	pixels[11] = 128
	line := fmt.Sprintf("[COMMAND] {\"status\":\"success\",\"chunks\":[{\"chunkX\":0,\"chunkZ\":0,\"layerCount\":1,\"image\":\"%s\"}]}\n",base64.StdEncoding.EncodeToString(pixels))
	if err:=os.WriteFile(logPath,[]byte(line),0600);err!=nil {t.Fatal(err)}
	n,err:=renderSampledPreview(logPath,output,8,8,16)
	if err!=nil || n!=1 {t.Fatalf("expected one real Minecraft chunk instead of 256 duplicates, got %d: %v",n,err)}
	f,err:=os.Open(output);if err!=nil {t.Fatal(err)}
	defer f.Close()
	img,err:=png.Decode(f);if err!=nil {t.Fatal(err)}
	r,g,b,_:=img.At(0,0).RGBA()
	if r>>8!=0x56 || g>>8!=0x34 || b>>8!=0x12 {
		t.Fatalf("MiEx BGRA decode wrong: %x,%x,%x",r>>8,g>>8,b>>8)
	}
	r,g,b,_=img.At(16,0).RGBA()
	if r>>8!=232 || g>>8!=232 || b>>8!=232 {
		t.Fatalf("transparent sample should reveal the gray checkerboard: %d,%d,%d", r>>8, g>>8, b>>8)
	}
	r,g,b,_=img.At(32,0).RGBA()
	blend:=func(source uint32)uint32{return (source*128+218*127+127)/255}
	if r>>8!=blend(0x56) || g>>8!=blend(0x34) || b>>8!=blend(0x12) {
		t.Fatalf("semi-transparent sample composite incorrect: %d,%d,%d", r>>8, g>>8, b>>8)
	}
	// Enlarging a 16x16 chunk must follow source pixel rows rather than
	// repeating the same complete image in every 16x16 output cell.
	bottomR, bottomG, bottomB, _ := img.At(0,16).RGBA()
	if bottomR>>8 != 0x9a || bottomG>>8 != 0x34 || bottomB>>8 != 0x12 {
		t.Fatalf("unexpected block color in second source row: %x,%x,%x", bottomR>>8,bottomG>>8,bottomB>>8)
	}
}

func TestPreviewOfUnexploredAreaIsClickableGrayMap(t *testing.T) {
	dir := t.TempDir()
	log := filepath.Join(dir, "miex.log")
	pngPath := filepath.Join(dir, "preview.png")
	if err := os.WriteFile(log, []byte("[COMMAND] {\"chunks\":[]}\n"), 0600); err != nil {
		t.Fatal(err)
	}
	count, err := renderSampledPreview(log, pngPath, 0, 0, 512)
	if err != nil || count != 0 {
		t.Fatalf("empty but valid MiEx chunk response should produce a gray map: %d, %v", count, err)
	}
	f, err := os.Open(pngPath)
	if err != nil {t.Fatal(err)}
	defer f.Close()
	img, err := png.Decode(f)
	if err != nil {t.Fatal(err)}
	r,g,b,_ := img.At(0,0).RGBA()
	if r>>8 != 218 || g>>8 != 218 || b>>8 != 218 {
		t.Fatalf("unsampled terrain must remain gray, got %d,%d,%d",r>>8,g>>8,b>>8)
	}
}

func TestPreviewRejectsMissingMiExChunkResponse(t *testing.T) {
	dir := t.TempDir()
	log := filepath.Join(dir, "miex.log")
	if err := os.WriteFile(log, []byte("[COMMAND] {\"status\":\"success\"}\n"), 0600); err != nil {
		t.Fatal(err)
	}
	_, err := renderSampledPreview(log, filepath.Join(dir,"preview.png"), 0,0,512)
	if err == nil {t.Fatal("a missing getChunk command response must not be shown as successful")}
}
