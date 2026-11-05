package main

import (
	"encoding/base64"
	"fmt"
	"image/png"
	"os"
	"path/filepath"
	"strings"
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

func TestPreviewRejectsCorruptLoadedChunkImage(t *testing.T) {
	dir := t.TempDir()
	log := filepath.Join(dir,"miex.log")
	for _, chunk := range []string{
		`{"chunkX":0,"chunkZ":0,"layerCount":1,"image":"broken!"}`,
		`{"chunkX":0,"chunkZ":0,"layerCount":1,"image":""}`,
		`{"chunkX":0,"chunkZ":0,"layerCount":1,"image":"AA=="}`,
	} {
		payload := "[COMMAND] " + `{"chunks":[` + chunk + `]}` + "\n"
		if err:=os.WriteFile(log,[]byte(payload),0600);err!=nil {t.Fatal(err)}
		if _,err:=renderSampledPreview(log, filepath.Join(dir,"map.png"), 8,8,16);err==nil {
			t.Fatalf("corrupt loaded chunk was accepted: %s",chunk)
		}
	}
}

func TestPreviewRejectsExplicitMiExFailure(t *testing.T) {
	dir := t.TempDir()
	log := filepath.Join(dir,"miex.log")
	payload := "[COMMAND] {\"status\":\"error\",\"chunks\":[]}\n"
	if err:=os.WriteFile(log,[]byte(payload),0600);err!=nil {t.Fatal(err)}
	_,err:=renderSampledPreview(log,filepath.Join(dir,"map.png"),0,0,512)
	if err==nil { t.Fatal("MiEx failure incorrectly rendered as an empty valid region") }
}

func TestPreviewRejectsNativeMiExFailureAfterSuccessfulBatch(t *testing.T) {
	dir := t.TempDir()
	logPath := filepath.Join(dir, "miex.log")
	output := filepath.Join(dir, "map.png")
	// MiEx printError emits status/error/stacktrace without a chunks field.
	// A later failed batch must not turn the earlier success into a partial map.
	payload := fmt.Sprintf("[COMMAND] {\"status\":\"success\",\"chunks\":[{\"chunkX\":0,\"chunkZ\":0,\"layerCount\":1,\"image\":\"%s\"}]}\n", solidChunkImage(234, 12, 24))
	payload += "[COMMAND] {\"status\":\"error\",\"error\":\"chunk database unavailable\",\"stacktrace\":[]}\n"
	if err := os.WriteFile(logPath, []byte(payload), 0600); err != nil {
		t.Fatal(err)
	}
	count, err := renderSampledPreview(logPath, output, 0, 0, 32)
	if count != 0 || err == nil || !strings.Contains(err.Error(), "chunk database unavailable") {
		t.Fatalf("native failure was hidden by an earlier batch: count=%d err=%v", count, err)
	}
	if _, err := os.Stat(output); !os.IsNotExist(err) {
		t.Fatalf("failed preview published a partial image: %v", err)
	}
}

func solidChunkImage(red, green, blue byte) string {
	pixels := make([]byte, 16*16*4)
	for i := 0; i < len(pixels); i += 4 {
		pixels[i] = blue
		pixels[i+1] = green
		pixels[i+2] = red
		pixels[i+3] = 255
	}
	return base64.StdEncoding.EncodeToString(pixels)
}

func TestPreviewPlacesNonAdjacentChunksAtTheirWorldCoordinates(t *testing.T) {
	dir := t.TempDir()
	logPath := filepath.Join(dir, "miex.log")
	output := filepath.Join(dir, "map.png")
	// 272 blocks span 17 chunks along each axis. The old large-region
	// renderer wrongly drew sparse samples in adjacent 16-pixel tiles.
	payload := fmt.Sprintf(
		"[COMMAND] {\"status\":\"success\",\"chunks\":[{\"chunkX\":5,\"chunkZ\":7,\"layerCount\":1,\"image\":\"%s\"},{\"chunkX\":6,\"chunkZ\":7,\"layerCount\":1,\"image\":\"%s\"}]}\n",
		solidChunkImage(225, 10, 20), solidChunkImage(15, 235, 20),
	)
	if err := os.WriteFile(logPath, []byte(payload), 0600); err != nil {
		t.Fatal(err)
	}
	n, err := renderSampledPreview(logPath, output, 136, 136, 272)
	if err != nil || n != 2 {
		t.Fatalf("expected two decoded chunks, got %d: %v", n, err)
	}
	file, err := os.Open(output)
	if err != nil {
		t.Fatal(err)
	}
	defer file.Close()
	img, err := png.Decode(file)
	if err != nil {
		t.Fatal(err)
	}
	check := func(x, y int, wantR, wantG, wantB uint32) {
		t.Helper()
		r, g, b, _ := img.At(x, y).RGBA()
		if r>>8 != wantR || g>>8 != wantG || b>>8 != wantB {
			t.Errorf("pixel (%d,%d): got %d,%d,%d want %d,%d,%d", x, y, r>>8, g>>8, b>>8, wantR, wantG, wantB)
		}
	}
	check(78, 110, 225, 10, 20)
	check(92, 110, 15, 235, 20)
	check(65, 110, 218, 218, 218) // Adjacent unsampled land stays gray, not relocated.
}

func TestPreviewPreservesNegativeChunkCoordinates(t *testing.T) {
	dir := t.TempDir()
	logPath := filepath.Join(dir, "miex.log")
	output := filepath.Join(dir, "map.png")
	payload := fmt.Sprintf("[COMMAND] {\"chunks\":[{\"chunkX\":-1,\"chunkZ\":-1,\"layerCount\":1,\"image\":\"%s\"}]}\n", solidChunkImage(22, 66, 177))
	if err := os.WriteFile(logPath, []byte(payload), 0600); err != nil {
		t.Fatal(err)
	}
	if _, err := renderSampledPreview(logPath, output, 0, 0, 32); err != nil {
		t.Fatal(err)
	}
	file, err := os.Open(output)
	if err != nil {
		t.Fatal(err)
	}
	defer file.Close()
	img, err := png.Decode(file)
	if err != nil {
		t.Fatal(err)
	}
	r, g, b, _ := img.At(0, 0).RGBA()
	if r>>8 != 22 || g>>8 != 66 || b>>8 != 177 {
		t.Fatalf("negative chunk displayed in the wrong position: %d,%d,%d", r>>8, g>>8, b>>8)
	}
	r, _, _, _ = img.At(128, 0).RGBA()
	if r>>8 != 218 {
		t.Fatalf("the neighboring unqueried chunk was incorrectly filled: %d", r>>8)
	}
}

func TestHugePreviewUsesAverageColorsRatherThanInventedBlockGeometry(t *testing.T) {
	dir := t.TempDir()
	logPath := filepath.Join(dir, "miex.log")
	output := filepath.Join(dir, "map.png")
	pixels := make([]byte, 16*16*4)
	for i := 0; i < 16*16; i++ {
		if i < 128 {
			pixels[4*i] = 255 // blue in BGRA
		} else {
			pixels[4*i+2] = 255 // red in BGRA
		}
		pixels[4*i+3] = 255
	}
	payload := fmt.Sprintf("[COMMAND] {\"chunks\":[{\"chunkX\":-64,\"chunkZ\":-64,\"layerCount\":1,\"image\":\"%s\"}]}\n", base64.StdEncoding.EncodeToString(pixels))
	if err := os.WriteFile(logPath, []byte(payload), 0600); err != nil {
		t.Fatal(err)
	}
	if _, err := renderSampledPreview(logPath, output, 0, 0, 2048); err != nil {
		t.Fatal(err)
	}
	file, err := os.Open(output)
	if err != nil {
		t.Fatal(err)
	}
	defer file.Close()
	img, err := png.Decode(file)
	if err != nil {
		t.Fatal(err)
	}
	r, g, b, _ := img.At(0, 0).RGBA()
	if r>>8 != 127 || g>>8 != 0 || b>>8 != 127 {
		t.Fatalf("coarse preview must use mean color, not raw texture pixels: %d,%d,%d", r>>8, g>>8, b>>8)
	}
}

func TestPreviewCombinesSeparateMiExChunkBatches(t *testing.T) {
	dir := t.TempDir()
	logPath := filepath.Join(dir, "miex.log")
	output := filepath.Join(dir, "preview.png")
	// The same exact chunk images now arrive as multiple getChunk responses,
	// each under the 64-chunk MiEx worker cap instead of one large response.
	one := fmt.Sprintf("[COMMAND] {\"status\":\"success\",\"chunks\":[{\"chunkX\":0,\"chunkZ\":0,\"layerCount\":1,\"image\":\"%s\"}]}\n", solidChunkImage(234, 12, 24))
	two := fmt.Sprintf("[COMMAND] {\"status\":\"success\",\"chunks\":[{\"chunkX\":1,\"chunkZ\":0,\"layerCount\":1,\"image\":\"%s\"}]}\n", solidChunkImage(13, 225, 33))
	if err := os.WriteFile(logPath, []byte(one+two), 0600); err != nil {
		t.Fatal(err)
	}
	count, err := renderSampledPreview(logPath, output, 16, 16, 32)
	if err != nil || count != 2 {
		t.Fatalf("chunk batches not combined: %d, %v", count, err)
	}
	f, err := os.Open(output)
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	img, err := png.Decode(f)
	if err != nil {
		t.Fatal(err)
	}
	r, g, b, _ := img.At(0, 0).RGBA()
	if r>>8 != 234 || g>>8 != 12 || b>>8 != 24 {
		t.Fatalf("first preview chunk changed: %d,%d,%d", r>>8, g>>8, b>>8)
	}
	r, g, b, _ = img.At(128, 0).RGBA()
	if r>>8 != 13 || g>>8 != 225 || b>>8 != 33 {
		t.Fatalf("second preview chunk changed: %d,%d,%d", r>>8, g>>8, b>>8)
	}
}


func TestPreviewRequiresEveryMiExBatch(t *testing.T) {
	dir := t.TempDir()
	logPath := filepath.Join(dir,"preview.log")
	imagePath := filepath.Join(dir,"preview.png")
	one := fmt.Sprintf("[COMMAND] {\"status\":\"success\",\"chunks\":[{\"chunkX\":0,\"chunkZ\":0,\"layerCount\":1,\"image\":\"%s\"}]}\n",solidChunkImage(44,55,66))
	if err := os.WriteFile(logPath,[]byte(one),0600);err!=nil {t.Fatal(err)}
	if _,err:=renderSampledPreviewExpected(logPath,imagePath,8,8,16,2);err==nil ||
		!strings.Contains(err.Error(),"only 1 of 2 requested preview batches") {
		t.Fatalf("missing MiEx chunk batch was not rejected: %v",err)
	}
	if _,err:=os.Stat(imagePath);!os.IsNotExist(err) {
		t.Fatalf("missing batch produced a misleading image: %v",err)
	}
	if _,err:=renderSampledPreviewExpected(logPath,imagePath,8,8,16,1);err!=nil {
		t.Fatalf("complete MiEx batch was rejected: %v",err)
	}
}

func TestPreviewBatchCountMatchesExporterChunkGrid(t *testing.T) {
	for _, sample := range []struct{ x,z,size,batches int } {
		{8,8,16,1},
		{0,0,1024,64},
		{4,-470,1024,67}, // Actual nonaligned Bedrock region: 65 x 65 chunks.
		{0,0,8192,144}, // Coarse 96 x 96 sample grid.
	} {
		if got:=previewBatchCount(sample.x,sample.z,sample.size);got!=sample.batches {
			t.Fatalf("preview (%d,%d) size %d: %d batches, expected %d",sample.x,sample.z,sample.size,got,sample.batches)
		}
	}
}
