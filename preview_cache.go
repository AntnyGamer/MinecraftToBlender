package main

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"image/png"
	"io"
	"io/fs"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"
)

const previewCacheFormat = "region-preview-v2"
const previewCacheLimit = 96

// Check every file's name, size and modification time, including Bedrock's
// LevelDB files. level.dat alone does not change when terrain is edited.
func previewWorldFingerprint(ctx context.Context, world string) (string, error) {
	hash := sha256.New()
	err := filepath.WalkDir(world, func(path string, entry fs.DirEntry, walkErr error) error {
		if err := ctx.Err(); err != nil { return err }
		if walkErr != nil { return walkErr }
		if entry.Type()&os.ModeSymlink != 0 {
			return fmt.Errorf("world contains a symbolic link: %s", path)
		}
		// Directory timestamps can change from indexing or a temporary
		// LevelDB helper without changes to saved terrain. Track saved files
		// rather than directory metadata so an unchanged world stays cached.
		if entry.IsDir() { return nil }
		info, err := entry.Info()
		if err != nil { return err }
		if !info.Mode().IsRegular() {
			return fmt.Errorf("world contains a non-regular file: %s", path)
		}
		rel, err := filepath.Rel(world, path)
		if err != nil { return err }
		_, _ = fmt.Fprintf(hash, "%s\x00%s\x00%d\x00%d\x00",
			filepath.ToSlash(rel), info.Mode().String(), info.Size(), info.ModTime().UnixNano())
		// Small world metadata files can change without changing length.
		// Hash their actual bytes as well. Terrain DB changes are tracked by
		// the metadata of every DB file, not just level.dat.
		if strings.EqualFold(entry.Name(), "level.dat") ||
			strings.EqualFold(entry.Name(), "level.dat_old") {
			f, err := os.Open(path)
			if err != nil { return err }
			_, copyErr := io.Copy(hash, f)
			closeErr := f.Close()
			if copyErr != nil { return copyErr }
			if closeErr != nil { return closeErr }
		}
		return nil
	})
	if err != nil { return "", err }
	return hex.EncodeToString(hash.Sum(nil)), nil
}

func previewCacheKey(world, edition, dimension string, packs bool, size, x, z int, version, fingerprint string) string {
	absolute, err := filepath.Abs(world)
	if err != nil { absolute = world }
	hash := sha256.New()
	_, _ = fmt.Fprintf(hash, "%s\x00%s\x00%s\x00%s\x00%t\x00%d\x00%d\x00%d\x00%s\x00%s",
		previewCacheFormat, strings.ToLower(filepath.Clean(absolute)), edition, dimension,
		packs, size, x, z, version, fingerprint)
	return hex.EncodeToString(hash.Sum(nil))
}

// A copied, temporary PNG is owned by the preview window; cached files must
// survive window closure and must never be passed to window cleanup directly.
func previewTempCopy(source, dir string) (string, error) {
	src, err := os.Open(source)
	if err != nil { return "", err }
	defer src.Close()
	dest, err := os.CreateTemp(dir, "Preview_*.png")
	if err != nil { return "", err }
	path := dest.Name()
	_, copyErr := io.Copy(dest, src)
	closeErr := dest.Close()
	if copyErr != nil || closeErr != nil {
		_ = os.Remove(path)
		if copyErr != nil { return "", copyErr }
		return "", closeErr
	}
	return path, nil
}

func cachedPreview(cacheFile, outputDir string) (string, bool) {
	f, err := os.Open(cacheFile)
	if err != nil { return "", false }
	img, decodeErr := png.Decode(f) // Validate the complete image, not just its header.
	closeErr := f.Close()
	if decodeErr != nil || closeErr != nil || img.Bounds().Dx() != 256 || img.Bounds().Dy() != 256 {
		return "", false
	}
	output, err := previewTempCopy(cacheFile, outputDir)
	if err != nil { return "", false }
	now := time.Now()
	_ = os.Chtimes(cacheFile, now, now) // Most recently used cache entry.
	return output, true
}

func storePreviewCache(source, dir, key string) error {
	if err := os.MkdirAll(dir, 0700); err != nil { return err }
	temp, err := previewTempCopy(source, dir)
	if err != nil { return err }
	target := filepath.Join(dir, key+".png")
	if err := os.Rename(temp, target); err != nil {
		// Windows cannot rename over an existing file. This entry is for the
		// same content key and already exists, so keep it rather than delete it.
		_ = os.Remove(temp)
		if _, statErr := os.Stat(target); statErr == nil { return nil }
		return err
	}
	trimPreviewCache(dir)
	return nil
}

func trimPreviewCache(dir string) {
	entries, err := os.ReadDir(dir)
	if err != nil { return }
	type candidate struct { path string; modified time.Time }
	files := make([]candidate, 0, len(entries))
	for _, entry := range entries {
		if entry.IsDir() || filepath.Ext(entry.Name()) != ".png" { continue }
		info, err := entry.Info()
		if err != nil || !info.Mode().IsRegular() { continue }
		files = append(files, candidate{filepath.Join(dir, entry.Name()), info.ModTime()})
	}
	if len(files) <= previewCacheLimit { return }
	sort.Slice(files, func(i, j int) bool { return files[i].modified.Before(files[j].modified) })
	for _, file := range files[:len(files)-previewCacheLimit] {
		_ = os.Remove(file.path)
	}
}

func previewCoordinates(minX, minZ, size, mouseX, mouseY int) (int, int, bool) {
	if size <= 0 || mouseX < 32 || mouseX >= 544 || mouseY < 70 || mouseY >= 582 {
		return 0, 0, false
	}
	return minX + (mouseX-32)*size/512, minZ + (mouseY-70)*size/512, true
}
