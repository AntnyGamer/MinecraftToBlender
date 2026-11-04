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
	for scanner.Scan() {
		line := scanner.Bytes()
		if len(line) < 30 || string(line[:10]) != "[COMMAND] " {
			continue
		}
		var response struct {
			Status string `json:"status"`
			Chunks []previewChunk `json:"chunks"`
		}
		if err := json.Unmarshal(line[10:], &response); err != nil || len(response.Chunks) == 0 {
			continue
		}
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
	if len(tiles) == 0 {
		return 0, fmt.Errorf("MiEx returned no readable chunk images at the selected coordinates")
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
	for row := 0; row < 16; row++ {
		for col := 0; col < 16; col++ {
			chunkX := int(math.Floor(float64(firstChunkX)+float64(lastChunkX-firstChunkX)*float64(col)/15))
			chunkZ := int(math.Floor(float64(firstChunkZ)+float64(lastChunkZ-firstChunkZ)*float64(row)/15))
			data, ok := tiles[[2]int{chunkX, chunkZ}]
			if !ok { continue }
			loaded++
			for py := 0; py < 16; py++ {
				for px := 0; px < 16; px++ {
					offset := (py*16+px)*4
					out.SetNRGBA(col*16+px, row*16+py, imgcolor.NRGBA{
						R: data[offset+2], G: data[offset+1], B: data[offset], A: 255,
					})
				}
			}
		}
	}
	if loaded == 0 {
		return 0, fmt.Errorf("the selected area has no readable chunk images")
	}
	dest, err := os.Create(output)
	if err != nil { return 0, err }
	defer dest.Close()
	if err := png.Encode(dest, out); err != nil { return 0, err }
	return loaded, nil
}
