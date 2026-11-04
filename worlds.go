package main

import (
	"bytes"
	"compress/gzip"
	"encoding/binary"
	"fmt"
	"io"
	"math"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"
)

type worldEdition string

const (
	bedrockEdition worldEdition = "bedrock"
	javaEdition    worldEdition = "java"
)

type localWorld struct {
	edition          worldEdition
	path, name, icon string
	played           time.Time
	exactDate        bool
	x, z             int
	hasCenter        bool
}

// Scan the ordinary Windows save locations, including both the new GDK and
// legacy UWP Bedrock layouts. Different Xbox IDs have separate GDK saves.
func worldRoots(edition worldEdition) []string {
	var roots []string
	add := func(p string) {
		if p != "" {
			roots = append(roots, p)
		}
	}
	appdata, local, home := os.Getenv("APPDATA"), os.Getenv("LOCALAPPDATA"), os.Getenv("USERPROFILE")
	if edition == bedrockEdition {
		for _, e := range []string{"Minecraft Bedrock", "Minecraft Bedrock Preview"} {
			if appdata == "" {
				break
			}
			base := filepath.Join(appdata, e, "Users")
			entries, _ := os.ReadDir(base)
			for _, v := range entries {
				if v.IsDir() {
					add(filepath.Join(base, v.Name(), "games", "com.mojang", "minecraftWorlds"))
				}
			}
		}
		if local != "" {
			for _, pkg := range []string{"Microsoft.MinecraftUWP_8wekyb3d8bbwe", "Microsoft.MinecraftWindowsBeta_8wekyb3d8bbwe"} {
				add(filepath.Join(local, "Packages", pkg, "LocalState", "games", "com.mojang", "minecraftWorlds"))
			}
		}
	} else {
		if appdata != "" {
			add(filepath.Join(appdata, ".minecraft", "saves"))
		}
		if home != "" {
			add(filepath.Join(home, ".minecraft", "saves"))
		}
		// Common modded launchers use their own instance directories.
		for _, pattern := range []string{
			filepath.Join(appdata, "PrismLauncher", "instances", "*", "minecraft", "saves"),
			filepath.Join(appdata, "MultiMC", "instances", "*", "minecraft", "saves"),
			filepath.Join(home, "curseforge", "minecraft", "Instances", "*", "saves"),
			filepath.Join(home, "Documents", "CurseForge", "Minecraft", "Instances", "*", "saves"),
			filepath.Join(appdata, "com.modrinth.theseus", "profiles", "*", "saves"),
			filepath.Join(appdata, "ATLauncher", "instances", "*", "saves"),
		} {
			if !filepath.IsAbs(pattern) {
				continue
			}
			if hits, _ := filepath.Glob(pattern); len(hits) > 0 {
				roots = append(roots, hits...)
			}
		}
	}
	return roots
}

func validWorldDir(path string, edition worldEdition) bool {
	if s, e := os.Stat(filepath.Join(path, "level.dat")); e != nil || s.IsDir() {
		return false
	}
	if edition == bedrockEdition {
		s, e := os.Stat(filepath.Join(path, "db"))
		return e == nil && s.IsDir()
	}
	if s, e := os.Stat(filepath.Join(path, "region")); e == nil && s.IsDir() {
		return true
	}
	if s, e := os.Stat(filepath.Join(path, "dimensions")); e == nil && s.IsDir() {
		return true
	}
	return false
}
func discoverWorlds(edition worldEdition, extraRoot string) []localWorld {
	roots := worldRoots(edition)
	if extraRoot != "" {
		// Accept either a world directory, a saves/minecraftWorlds directory,
		// or a parent game directory chosen in Explorer.
		roots = append([]string{extraRoot, filepath.Join(extraRoot, "saves"), filepath.Join(extraRoot, "minecraftWorlds")}, roots...)
	}
	seen := map[string]bool{}
	var found []localWorld
	for _, root := range roots {
		// Explicitly selected folder may itself be a world.
		candidates := []string{}
		if validWorldDir(root, edition) {
			candidates = append(candidates, root)
		} else {
			entries, e := os.ReadDir(root)
			if e != nil {
				continue
			}
			for _, v := range entries {
				if v.IsDir() {
					candidates = append(candidates, filepath.Join(root, v.Name()))
				}
			}
		}
		for _, p := range candidates {
			key := strings.ToLower(filepath.Clean(p))
			if seen[key] {
				continue
			}
			if !validWorldDir(p, edition) {
				continue
			}
			seen[key] = true
			found = append(found, readWorldInfo(p, edition))
		}
	}
	sort.SliceStable(found, func(i, j int) bool {
		if found[i].played.Equal(found[j].played) {
			return strings.ToLower(found[i].name) < strings.ToLower(found[j].name)
		}
		return found[i].played.After(found[j].played)
	})
	return found
}
func readWorldInfo(p string, edition worldEdition) localWorld {
	v := localWorld{path: p, edition: edition, name: filepath.Base(p)}
	if edition == bedrockEdition {
		v.icon = filepath.Join(p, "world_icon.jpeg")
	} else {
		v.icon = filepath.Join(p, "icon.png")
	}
	if _, e := os.Stat(v.icon); e != nil {
		v.icon = ""
	}
	level := filepath.Join(p, "level.dat")
	if info, e := os.Stat(level); e == nil {
		v.played = info.ModTime()
	}
	gotMetadataName := false
	if metadata, e := readLevelDat(level, edition); e == nil {
		if metadata.Name != "" {
			v.name = metadata.Name
			gotMetadataName = true
		}
		if !metadata.LastPlayed.IsZero() {
			v.played = metadata.LastPlayed
			v.exactDate = true
		}
		if metadata.HasCenter {
			v.x, v.z, v.hasCenter = metadata.X, metadata.Z, true
		}
	}
	// level.dat takes precedence over levelname.txt. Read the fallback only
	// when it can actually affect the displayed Bedrock world name.
	if edition == bedrockEdition && !gotMetadataName {
		if b, e := os.ReadFile(filepath.Join(p, "levelname.txt")); e == nil {
			if x := strings.TrimSpace(strings.TrimPrefix(string(bytes.TrimRight(b, "\x00")), "\ufeff")); x != "" {
				v.name = x
			}
		}
	}
	return v
}

type worldMeta struct {
	Name         string
	LastPlayed   time.Time
	X, Z         int
	HasCenter    bool
	sx, sz       int
	hasSX, hasSZ bool
	px, pz       float64
	hasPX, hasPZ bool
}

// Read only metadata. Never load, open, or rewrite region/LevelDB files.
func readLevelDat(path string, edition worldEdition) (worldMeta, error) {
	f, e := os.Open(path)
	if e != nil {
		return worldMeta{}, e
	}
	defer f.Close()
	var r io.Reader = f
	var order binary.ByteOrder = binary.LittleEndian
	if edition == javaEdition {
		order = binary.BigEndian
		gz, e := gzip.NewReader(f)
		if e != nil {
			return worldMeta{}, e
		}
		defer gz.Close()
		r = gz
	} else {
		var hdr [8]byte
		if _, e = io.ReadFull(f, hdr[:]); e != nil {
			return worldMeta{}, e
		}
	}
	raw, e := io.ReadAll(io.LimitReader(r, 16<<20))
	if e != nil {
		return worldMeta{}, e
	}
	nb := nbtReader{raw: raw, order: order}
	tag, e := nb.u8()
	if e != nil || tag != 10 {
		return worldMeta{}, fmt.Errorf("invalid level.dat root")
	}
	if _, e = nb.str(); e != nil {
		return worldMeta{}, e
	}
	m := worldMeta{}
	if e = nb.compound("", 0, &m); e != nil {
		return m, e
	}
	if m.hasPX && m.hasPZ && !math.IsNaN(m.px) && !math.IsNaN(m.pz) &&
		!math.IsInf(m.px, 0) && !math.IsInf(m.pz, 0) {
		m.X, m.Z = int(math.Floor(m.px)), int(math.Floor(m.pz))
		m.HasCenter = true
	} else if m.hasSX && m.hasSZ {
		m.X, m.Z = m.sx, m.sz
		m.HasCenter = true
	}
	return m, nil
}

type nbtReader struct {
	raw   []byte
	off   int
	order binary.ByteOrder
}

func (n *nbtReader) take(k int) ([]byte, error) {
	if k < 0 || k > len(n.raw)-n.off {
		return nil, io.ErrUnexpectedEOF
	}
	x := n.raw[n.off : n.off+k]
	n.off += k
	return x, nil
}
func (n *nbtReader) u8() (byte, error) {
	b, e := n.take(1)
	if e != nil {
		return 0, e
	}
	return b[0], nil
}
func (n *nbtReader) i16() (int, error) {
	b, e := n.take(2)
	if e != nil {
		return 0, e
	}
	return int(n.order.Uint16(b)), nil
}
func (n *nbtReader) i32() (int32, error) {
	b, e := n.take(4)
	if e != nil {
		return 0, e
	}
	return int32(n.order.Uint32(b)), nil
}
func (n *nbtReader) i64() (int64, error) {
	b, e := n.take(8)
	if e != nil {
		return 0, e
	}
	return int64(n.order.Uint64(b)), nil
}
func (n *nbtReader) str() (string, error) {
	k, e := n.i16()
	if e != nil {
		return "", e
	}
	b, e := n.take(k)
	return string(b), e
}
func (n *nbtReader) compound(path string, depth int, m *worldMeta) error {
	if depth > 48 {
		return fmt.Errorf("NBT nesting too deep")
	}
	for {
		tag, e := n.u8()
		if e != nil {
			return e
		}
		if tag == 0 {
			return nil
		}
		name, e := n.str()
		if e != nil {
			return e
		}
		field := path + "/" + name
		if e = n.value(tag, field, depth+1, m); e != nil {
			return e
		}
	}
}
func (n *nbtReader) value(tag byte, path string, depth int, m *worldMeta) error {
	if depth > 48 {
		return fmt.Errorf("NBT nesting too deep")
	}
	switch tag {
	case 1:
		_, e := n.take(1)
		return e
	case 2:
		_, e := n.take(2)
		return e
	case 3:
		v, e := n.i32()
		if e != nil {
			return e
		}
		if strings.HasSuffix(path, "/SpawnX") {
			m.sx = int(v)
			m.hasSX = true
		}
		if strings.HasSuffix(path, "/SpawnZ") {
			m.sz = int(v)
			m.hasSZ = true
		}
		return nil
	case 4:
		v, e := n.i64()
		if e != nil {
			return e
		}
		if strings.HasSuffix(path, "/LastPlayed") && v > 0 {
			seconds := v
			if v > 100000000000 {
				seconds = v / 1000
			}
			if seconds > 946684800 && seconds < 4102444800 {
				m.LastPlayed = time.Unix(seconds, 0)
			}
		}
		return nil
	case 5:
		_, e := n.take(4)
		return e
	case 6:
		_, e := n.take(8)
		return e
	case 7:
		k, e := n.i32()
		if e != nil {
			return e
		}
		_, e = n.take(int(k))
		return e
	case 8:
		v, e := n.str()
		if e != nil {
			return e
		}
		if strings.HasSuffix(path, "/LevelName") && v != "" {
			m.Name = v
		}
		return nil
	case 9:
		t, e := n.u8()
		if e != nil {
			return e
		}
		count, e := n.i32()
		if e != nil {
			return e
		}
		if count < 0 || count > 500000 {
			return fmt.Errorf("invalid NBT list length")
		}
		if strings.HasSuffix(path, "/Player/Pos") && t == 6 && count >= 3 {
			for i := int32(0); i < count; i++ {
				b, e := n.take(8)
				if e != nil {
					return e
				}
				f := math.Float64frombits(n.order.Uint64(b))
				if i == 0 {
					m.px = f
					m.hasPX = true
				}
				if i == 2 {
					m.pz = f
					m.hasPZ = true
				}
			}
			return nil
		}
		for i := int32(0); i < count; i++ {
			if e = n.value(t, path, depth+1, m); e != nil {
				return e
			}
		}
		return nil
	case 10:
		return n.compound(path, depth, m)
	case 11:
		k, e := n.i32()
		if e != nil {
			return e
		}
		if k < 0 || k > 5000000 {
			return fmt.Errorf("invalid NBT int array")
		}
		_, e = n.take(int(k) * 4)
		return e
	case 12:
		k, e := n.i32()
		if e != nil {
			return e
		}
		if k < 0 || k > 3000000 {
			return fmt.Errorf("invalid NBT long array")
		}
		_, e = n.take(int(k) * 8)
		return e
	default:
		return fmt.Errorf("unsupported NBT type %d", tag)
	}
}
