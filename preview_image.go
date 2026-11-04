package main

import (
	"bufio"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"image"
	imgcolor "image/color"
	"image/png"
	"math"
	"os"
)

type previewChunk struct {
	X int `json:"chunkX"`
	Z int `json:"chunkZ"`
	Image string `json:"image"`
	LayerCount int `json:"layerCount"`
}

func renderSampledPreview(logPath, output string, centerX, centerZ, size int) (int, error) {
	file, err := os.Open(logPath)
	if err != nil {
		return 0, err
	}
	defer file.Close()
	scanner := bufio.NewScanner(file)
	scanner.Buffer(make([]byte, 64*1024), 32*1024*1024)
	tiles := make(map[[2]int][]byte)
	sawChunkResponse := false
	for scanner.Scan() {
		line := scanner.Bytes()
		if len(line) < 30 || string(line[:10]) != "[COMMAND] " {
			continue
		}
		var response struct {
			Status string `json:"status"`
			Chunks []previewChunk `json:"chunks"`
		}
		if err := json.Unmarshal(line[10:], &response); err != nil || response.Chunks == nil {
			continue
		}
		sawChunkResponse = true
		for _, ch := range response.Chunks {
			if ch.Image == "" || ch.LayerCount <= 0 {
				continue
			}
			bytes, err := base64.StdEncoding.DecodeString(ch.Image)
			if err == nil && len(bytes) == 16*16*4 {
				// MiEx uses a zeroed image when it cannot render this chunk.
				visible := false
				for i := 3; i < len(bytes); i += 4 {
					if bytes[i] != 0 {visible = true; break}
				}
				if visible { tiles[[2]int{ch.X, ch.Z}] = bytes }
			}
		}
	}
	if err := scanner.Err(); err != nil {
		return 0, fmt.Errorf("read MiEx preview diagnostics: %w", err)
	}
	if !sawChunkResponse {
		return 0, fmt.Errorf("MiEx returned no valid chunk-preview response; inspect the command log")
	}
	out := image.NewNRGBA(image.Rect(0, 0, 256, 256))
	for y := 0; y < 256; y++ {
		for x := 0; x < 256; x++ {
			col := uint8(232)
			if ((x/16)+(y/16))%2 == 0 { col = 218 }
			out.SetNRGBA(x, y, imgcolor.NRGBA{R: col, G: col, B: col, A: 255})
		}
	}
	minX := centerX - size/2
	minZ := centerZ - size/2
	firstChunkX := int(math.Floor(float64(minX)/16))
	firstChunkZ := int(math.Floor(float64(minZ)/16))
	lastChunkX := int(math.Floor(float64(minX+size-1)/16))
	lastChunkZ := int(math.Floor(float64(minZ+size-1)/16))
	loaded := 0
	paintPixel := func(x,y int,data []byte,offset int) {
		alpha := data[offset+3]
		if alpha == 0 {
			return
		}
		pixel := imgcolor.NRGBA{R: data[offset+2], G: data[offset+1], B: data[offset], A: 255}
		if alpha < 255 {
			bg := out.NRGBAAt(x,y)
			blend := func(source, background uint8) uint8 {
				return uint8((uint32(source)*uint32(alpha) + uint32(background)*uint32(255-alpha) + 127) / 255)
			}
			pixel.R = blend(pixel.R,bg.R)
			pixel.G = blend(pixel.G,bg.G)
			pixel.B = blend(pixel.B,bg.B)
		}
		out.SetNRGBA(x,y,pixel)
	}
	// When all chunks fit within the 16x16 sample grid, display their exact
	// Minecraft positions. Repeating one tiny chunk 256 times made a false
	// tiled overview instead of a correctly enlarged map of those blocks.
	if lastChunkX-firstChunkX < 16 && lastChunkZ-firstChunkZ < 16 {
		seen := make(map[[2]int]bool)
		for y:=0;y<256;y++ {
			worldZ:=minZ+y*size/256
			chunkZ:=int(math.Floor(float64(worldZ)/16))
			localZ:=((worldZ%16)+16)%16
			for x:=0;x<256;x++ {
				worldX:=minX+x*size/256
				chunkX:=int(math.Floor(float64(worldX)/16))
				data,ok:=tiles[[2]int{chunkX,chunkZ}]
				if !ok {continue}
				seen[[2]int{chunkX,chunkZ}]=true
				localX:=((worldX%16)+16)%16
				paintPixel(x,y,data,(localZ*16+localX)*4)
			}
		}
		loaded=len(seen)
	} else {
		// Larger regions use a coarse 16x16 sample preview, never a claim of
		// full terrain coverage. Each cell displays the corresponding sampled
		// chunk image; genuinely unavailable chunks retain the gray grid.
		for row := 0; row < 16; row++ {
			for col := 0; col < 16; col++ {
				chunkX := int(math.Floor(float64(firstChunkX)+float64(lastChunkX-firstChunkX)*float64(col)/15))
				chunkZ := int(math.Floor(float64(firstChunkZ)+float64(lastChunkZ-firstChunkZ)*float64(row)/15))
				data, ok := tiles[[2]int{chunkX, chunkZ}]
				if !ok {continue}
				loaded++
				for py:=0;py<16;py++ {
					for px:=0;px<16;px++ {
						paintPixel(col*16+px,row*16+py,data,(py*16+px)*4)
					}
				}
			}
		}
	}
	// A valid empty region is an informative, all-gray preview, not a
	// command failure. It can still be clicked to change the export center.
	dest, err := os.Create(output)
	if err != nil { return 0, err }
	defer dest.Close()
	if err := png.Encode(dest, out); err != nil { return 0, err }
	// Report unique real chunk images, not repeated visual grid cells.
	return len(tiles), nil
}
