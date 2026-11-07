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

// Existing small fixtures intentionally omit unspecified chunks; the
// production path additionally checks that every requested MiEx batch replied.
func renderSampledPreview(logPath, output string, centerX, centerZ, size int) (int, error) {
	return renderSampledPreviewExpected(logPath, output, centerX, centerZ, size, 0)
}

func previewBatchCount(centerX, centerZ, size int) int {
	minX, minZ := centerX-size/2, centerZ-size/2
	firstX, firstZ := int(math.Floor(float64(minX)/16)), int(math.Floor(float64(minZ)/16))
	lastX, lastZ := int(math.Floor(float64(minX+size-1)/16)), int(math.Floor(float64(minZ+size-1)/16))
	spanX, spanZ := lastX-firstX+1, lastZ-firstZ+1
	if spanX<=0 || spanZ<=0 { return 0 }
	// Matches Get-PreviewChunkCoordinates in Export_World.ps1.
	chunks := spanX*spanZ
	if chunks>9216 { chunks=min(96,spanX)*min(96,spanZ) }
	// The exporter retries the very first (possibly cold) MiEx response last.
	return (chunks+63)/64 + 1
}

func renderSampledPreviewExpected(logPath, output string, centerX, centerZ, size, expectedBatches int) (int, error) {
	file, err := os.Open(logPath)
	if err != nil {
		return 0, err
	}
	defer file.Close()
	scanner := bufio.NewScanner(file)
	scanner.Buffer(make([]byte, 64*1024), 32*1024*1024)
	// Huge regions use one averaged color per sampled chunk. Retaining every
	// 1,024-byte BGRA tile would waste several MiB only to average it later.
	minX, minZ := centerX-size/2, centerZ-size/2
	firstChunkX, firstChunkZ := int(math.Floor(float64(minX)/16)), int(math.Floor(float64(minZ)/16))
	lastChunkX, lastChunkZ := int(math.Floor(float64(minX+size-1)/16)), int(math.Floor(float64(minZ+size-1)/16))
	spanX, spanZ := lastChunkX-firstChunkX+1, lastChunkZ-firstChunkZ+1
	exact := spanX*spanZ <= 9216
	var tiles map[[2]int][]byte
	var average map[[2]int]imgcolor.NRGBA
	if exact {
		tiles = make(map[[2]int][]byte)
	} else {
		average = make(map[[2]int]imgcolor.NRGBA)
	}
	// Coarse samples are averaged immediately, so their base64 decoder can
	// reuse one small buffer rather than allocating per sampled chunk.
	const chunkImageBytes = 16*16*4
	var coarsePixels [chunkImageBytes+2]byte
	sawChunkResponse := false
	batches := 0
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
		batches++
		for _, ch := range response.Chunks {
			// The image bytes are the source of truth. MiEx may omit layer
			// metadata even when it returned a valid colored preview tile.
			// Do not discard those real pixels as missing terrain.
			if ch.Image == "" {
				if ch.LayerCount <= 0 {
					continue // An actually absent chunk stays gray.
				}
				return 0, fmt.Errorf("MiEx omitted image data for loaded chunk (%d,%d)", ch.X, ch.Z)
			}
			var pixels []byte
			var err error
			if exact || len(ch.Image) > base64.StdEncoding.EncodedLen(chunkImageBytes) {
				// Exact maps must retain each tile; oversized malformed input takes
				// the allocating path to avoid overflowing the fixed scratch buffer.
				pixels, err = base64.StdEncoding.DecodeString(ch.Image)
			} else {
				var n int
				n, err = base64.StdEncoding.Decode(coarsePixels[:], []byte(ch.Image))
				pixels = coarsePixels[:n]
			}
			if err != nil || len(pixels) != chunkImageBytes {
				return 0, fmt.Errorf("MiEx returned an invalid image for chunk (%d,%d): %d bytes", ch.X, ch.Z, len(pixels))
			}
			// MiEx uses a zeroed image when it cannot render this chunk.
			visible := false
			for i := 3; i < len(pixels); i += 4 {
				if pixels[i] != 0 {visible = true; break}
			}
			if visible {
				key := [2]int{ch.X, ch.Z}
				if exact {
					tiles[key] = pixels
				} else {
					var red, green, blue, weight uint64
					for i := 0; i < len(pixels); i += 4 {
						a := uint64(pixels[i+3])
						red += uint64(pixels[i+2]) * a
						green += uint64(pixels[i+1]) * a
						blue += uint64(pixels[i]) * a
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
			}
		}
	}
	if err := scanner.Err(); err != nil {
		return 0, fmt.Errorf("read MiEx preview diagnostics: %w", err)
	}
	if !sawChunkResponse {
		return 0, fmt.Errorf("MiEx returned no valid chunk-preview response; inspect the command log")
	}
	if expectedBatches > 0 && batches != expectedBatches {
		return 0, fmt.Errorf("MiEx returned only %d of %d requested preview batches; refusing a partial map", batches, expectedBatches)
	}
	out := image.NewNRGBA(image.Rect(0, 0, 256, 256))
	// Fill this fixed, in-bounds pixel buffer directly. It produces the exact
	// same checkerboard while avoiding 65,536 image.SetNRGBA method calls.
	for y := 0; y < 256; y++ {
		row := out.Pix[y*out.Stride : y*out.Stride+256*4]
		for x := 0; x < 256; x++ {
			col := uint8(232)
			if ((x/16)+(y/16))%2 == 0 {
				col = 218
			}
			pixel := row[x*4 : x*4+4]
			pixel[0], pixel[1], pixel[2], pixel[3] = col, col, col, 255
		}
	}
	// Within the 9,216-chunk limit every source chunk is queried. Draw
	// exact block positions instead of inventing terrain between samples.
	paintPixel := func(x, y int, data []byte, offset int) {
		alpha := data[offset+3]
		if alpha == 0 {
			return
		}
		// All callers use 0..255 pixel coordinates in the fixed-size map.
		// Write the same opaque or alpha-blended RGB bytes directly, avoiding
		// a paired NRGBAAt/SetNRGBA call for every sampled Minecraft block.
		start := y*out.Stride + x*4
		pixel := out.Pix[start : start+4]
		if alpha < 255 {
			blend := func(source, background uint8) uint8 {
				return uint8((uint32(source)*uint32(alpha) + uint32(background)*uint32(255-alpha) + 127) / 255)
			}
			pixel[0] = blend(data[offset+2], pixel[0])
			pixel[1] = blend(data[offset+1], pixel[1])
			pixel[2] = blend(data[offset], pixel[2])
		} else {
			pixel[0], pixel[1], pixel[2] = data[offset+2], data[offset+1], data[offset]
		}
		pixel[3] = 255
	}
	// Every output column/row maps to a single world coordinate.
	// Compute those mappings once instead of repeating float division and
	// modulus for each of the 65,536 output pixels.
	var chunkXAt, chunkZAt, localXAt, localZAt [256]int
	for i := 0; i < 256; i++ {
		worldX, worldZ := minX+i*size/256, minZ+i*size/256
		// Signed right shift is floor division for both positive and
		// negative chunk coordinates; & 15 is the matching local offset.
		chunkXAt[i], chunkZAt[i] = worldX>>4, worldZ>>4
		localXAt[i], localZAt[i] = worldX&15, worldZ&15
	}
	if exact {
		for y := 0; y < 256; y++ {
			chunkZ, localZ := chunkZAt[y], localZAt[y]
			for x := 0; x < 256; x++ {
				data, ok := tiles[[2]int{chunkXAt[x], chunkZ}]
				if !ok {
					continue // Missing or unloaded chunks remain visibly gray.
				}
				paintPixel(x, y, data, (localZ*16+localXAt[x])*4)
			}
		}
	} else {
		// Very large regions cannot cheaply fetch every chunk. Show a coarse
		// color overview instead of falsely stitching distant 16x16 block
		// textures together and suggesting non-existent rivers or buildings.
		// Colors were accumulated while decoding, with no BGRA tile retention.
		nearestSample := func(chunk, first, last int) int {
			samples := min(96, last-first+1)
			if samples <= 1 {
				return first
			}
			index := int(math.Round(float64(chunk-first) * float64(samples-1) / float64(last-first)))
			index = max(0, min(samples-1, index))
			return first + int(math.Floor(float64(last-first)*float64(index)/float64(samples-1)))
		}
		var sampleXAt, sampleZAt [256]int
		for i := 0; i < 256; i++ {
			sampleXAt[i] = nearestSample(chunkXAt[i], firstChunkX, lastChunkX)
			sampleZAt[i] = nearestSample(chunkZAt[i], firstChunkZ, lastChunkZ)
		}
		for y := 0; y < 256; y++ {
			sampleZ := sampleZAt[y]
			for x := 0; x < 256; x++ {
				if pixel, ok := average[[2]int{sampleXAt[x], sampleZ}]; ok {
					start := y*out.Stride + x*4
					out.Pix[start], out.Pix[start+1], out.Pix[start+2], out.Pix[start+3] =
						pixel.R, pixel.G, pixel.B, pixel.A
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
	if exact {
		return len(tiles), nil
	}
	return len(average), nil
}
