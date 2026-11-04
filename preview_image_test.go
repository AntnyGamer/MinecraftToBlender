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
	line := fmt.Sprintf("[COMMAND] {\"status\":\"success\",\"chunks\":[{\"chunkX\":0,\"chunkZ\":0,\"image\":\"%s\"}]}\n",base64.StdEncoding.EncodeToString(pixels))
	if err:=os.WriteFile(logPath,[]byte(line),0600);err!=nil {t.Fatal(err)}
	n,err:=renderSampledPreview(logPath,output,0,0,16)
	if err!=nil || n!=256 {t.Fatalf("expected 256 duplicated sampled tiles, got %d: %v",n,err)}
	f,err:=os.Open(output);if err!=nil {t.Fatal(err)}
	defer f.Close()
	img,err:=png.Decode(f);if err!=nil {t.Fatal(err)}
	r,g,b,_:=img.At(0,0).RGBA()
	if r>>8!=0x56 || g>>8!=0x34 || b>>8!=0x12 {
		t.Fatalf("MiEx BGRA decode wrong: %x,%x,%x",r>>8,g>>8,b>>8)
	}
}
