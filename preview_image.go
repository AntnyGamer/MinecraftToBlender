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
		if len(line) < 10 || string(line[:10]) != "[COMMAND] " {
			continue
		}
		var response struct {
			Status string `json:"status"`
			Error string `json:"error"`
			Chunks []previewChunk `json:"chunks"`
		}
		if err := json.Unmarshal(line[10:], &response); err != nil {
			continue
		}
		if response.Status != "" && response.Status != "success" {
			message := response.Error
			if message == "" {
				message = response.Status
			}
			return 0, fmt.Errorf("MiEx rejected a preview command: %s", message)
		}
		if response.Chunks == nil {
			continue
		}
		sawChunkResponse = true
		for _, ch := range response.Chunks {
			if ch.LayerCount <= 0 {
				continue // Missing/empty terrain is a legitimate gray tile.
			}
			if ch.Image == "" {
				return 0, fmt.Errorf("MiEx omitted image data for loaded chunk (%d,%d)", ch.X, ch.Z)
			}
			pixels, err := base64.StdEncoding.DecodeString(ch.Image)
			if err != nil || len(pixels) != 16*16*4 {
				return 0, fmt.Errorf("MiEx returned an invalid image for chunk (%d,%d): %d bytes", ch.X, ch.Z, len(pixels))
			}
			// MiEx uses a zeroed image when it cannot render this chunk.
			visible := false
			for i := 3; i < len(pixels); i += 4 {
				if pixels[i] != 0 {visible = true; break}
			}
			if visible { tiles[[2]int{ch.X, ch.Z}] = pixels }
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
			if ((x/16)+(y/16))%2 == 0 {
				col = 218
			}
			out.SetNRGBA(x, y, imgcolor.NRGBA{R: col, G: col, B: col, A: 255})
		}
	}
	minX := centerX - size/2
	minZ := centerZ - size/2
	firstChunkX := int(math.Floor(float64(minX) / 16))
	firstChunkZ := int(math.Floor(float64(minZ) / 16))
	lastChunkX := int(math.Floor(float64(minX+size-1) / 16))
	lastChunkZ := int(math.Floor(float64(minZ+size-1) / 16))
	spanX := lastChunkX - firstChunkX + 1
	spanZ := lastChunkZ - firstChunkZ + 1
	// Match the 9,216-chunk upper bound used by Export_World.ps1.
	// Within that limit every source chunk is queried, so draw every pixel
	// at its real Minecraft block coordinate rather than stretching 16
	// noncontiguous samples into a deceptively continuous terrain map.
	exact := spanX*spanZ <= 9216
	paintPixel := func(x, y int, data []byte, offset int) {
		alpha := data[offset+3]
		if alpha == 0 {
			return
		}
		pixel := imgcolor.NRGBA{R: data[offset+2], G: data[offset+1], B: data[offset], A: 255}
		if alpha < 255 {
			bg := out.NRGBAAt(x, y)
			blend := func(source, background uint8) uint8 {
				return uint8((uint32(source)*uint32(alpha) + uint32(background)*uint32(255-alpha) + 127) / 255)
			}
			pixel.R = blend(pixel.R, bg.R)
			pixel.G = blend(pixel.G, bg.G)
			pixel.B = blend(pixel.B, bg.B)
		}
		out.SetNRGBA(x, y, pixel)
	}
	if exact {
		for y := 0; y < 256; y++ {
			worldZ := minZ + y*size/256
			chunkZ := int(math.Floor(float64(worldZ) / 16))
			localZ := ((worldZ % 16) + 16) % 16
			for x := 0; x < 256; x++ {
				worldX := minX + x*size/256
				chunkX := int(math.Floor(float64(worldX) / 16))
				data, ok := tiles[[2]int{chunkX, chunkZ}]
				if !ok {
					continue // Missing or unloaded chunks remain visibly gray.
				}
				localX := ((worldX % 16) + 16) % 16
				paintPixel(x, y, data, (localZ*16+localX)*4)
			}
		}
	} else {
		// Very large regions cannot cheaply fetch every chunk. Show a coarse
		// color overview instead of falsely stitching distant 16x16 block
		// textures together and suggesting non-existent rivers or buildings.
		average := make(map[[2]int]imgcolor.NRGBA, len(tiles))
		for key, data := range tiles {
			var red, green, blue, weight uint64
			for i := 0; i < len(data); i += 4 {
				a := uint64(data[i+3])
				red += uint64(data[i+2]) * a
				green += uint64(data[i+1]) * a
				blue += uint64(data[i]) * a
				weight += a
			}
			if weight > 0 {
				average[key] = imgcolor.NRGBA{
					R: uint8(red / weight),
					G: uint8(green / weight),
					B: uint8(blue / weight),
					A: 255,
				}
			}
		}
		nearestSample := func(chunk, first, last int) int {
			samples := min(96, last-first+1)
			if samples <= 1 {
				return first
			}
			index := int(math.Round(float64(chunk-first) * float64(samples-1) / float64(last-first)))
			index = max(0, min(samples-1, index))
			return first + int(math.Floor(float64(last-first)*float64(index)/float64(samples-1)))
		}
		for y := 0; y < 256; y++ {
			worldZ := minZ + y*size/256
			chunkZ := int(math.Floor(float64(worldZ) / 16))
			sampleZ := nearestSample(chunkZ, firstChunkZ, lastChunkZ)
			for x := 0; x < 256; x++ {
				worldX := minX + x*size/256
				chunkX := int(math.Floor(float64(worldX) / 16))
				sampleX := nearestSample(chunkX, firstChunkX, lastChunkX)
				if pixel, ok := average[[2]int{sampleX, sampleZ}]; ok {
					out.SetNRGBA(x, y, pixel)
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
