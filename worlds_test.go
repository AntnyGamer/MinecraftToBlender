package main

import (
	"bytes"
	"compress/gzip"
	"encoding/binary"
	"os"
	"path/filepath"
	"testing"
	"time"
)

func fixtureNBT(order binary.ByteOrder, name string, when int64, x, z int32) []byte {
	var b bytes.Buffer
	b.WriteByte(10)
	_ = binary.Write(&b, order, uint16(0))
	for _, tag := range []struct{ name, value string }{{"LevelName", name}} {
		b.WriteByte(8)
		_ = binary.Write(&b, order, uint16(len(tag.name)))
		b.WriteString(tag.name)
		_ = binary.Write(&b, order, uint16(len(tag.value)))
		b.WriteString(tag.value)
	}
	b.WriteByte(4)
	_ = binary.Write(&b, order, uint16(len("LastPlayed")))
	b.WriteString("LastPlayed")
	_ = binary.Write(&b, order, when)
	for _, field := range []struct {
		name  string
		value int32
	}{{"SpawnX", x}, {"SpawnZ", z}} {
		b.WriteByte(3)
		_ = binary.Write(&b, order, uint16(len(field.name)))
		b.WriteString(field.name)
		_ = binary.Write(&b, order, field.value)
	}
	b.WriteByte(0)
	return b.Bytes()
}

func writeFixtureWorld(t *testing.T, path string, edition worldEdition, name string, played int64) {
	t.Helper()
	subfolder := "region"
	if edition == bedrockEdition {
		subfolder = "db"
	}
	if err := os.MkdirAll(filepath.Join(path, subfolder), 0755); err != nil {
		t.Fatal(err)
	}
	var out bytes.Buffer
	if edition == javaEdition {
		gz := gzip.NewWriter(&out)
		if _, err := gz.Write(fixtureNBT(binary.BigEndian, name, played*1000, 12, -34)); err != nil {
			t.Fatal(err)
		}
		if err := gz.Close(); err != nil {
			t.Fatal(err)
		}
	} else {
		raw := fixtureNBT(binary.LittleEndian, name, played, 45, -55)
		_ = binary.Write(&out, binary.LittleEndian, uint32(10))
		_ = binary.Write(&out, binary.LittleEndian, uint32(len(raw)))
		out.Write(raw)
	}
	if err := os.WriteFile(filepath.Join(path, "level.dat"), out.Bytes(), 0644); err != nil {
		t.Fatal(err)
	}
}

func TestMetadataForBothEditions(t *testing.T) {
	for _, tt := range []struct {
		edition worldEdition
		x, z    int
	}{{javaEdition, 12, -34}, {bedrockEdition, 45, -55}} {
		path := filepath.Join(t.TempDir(), string(tt.edition))
		writeFixtureWorld(t, path, tt.edition, "Example world", 1750000000)
		if !validWorldDir(path, tt.edition) {
			t.Fatalf("valid %s world rejected", tt.edition)
		}
		got, err := readLevelDat(filepath.Join(path, "level.dat"), tt.edition)
		if err != nil {
			t.Fatal(err)
		}
		if got.Name != "Example world" || got.X != tt.x || got.Z != tt.z || !got.HasCenter || got.LastPlayed.Unix() != 1750000000 {
			t.Fatalf("%s metadata incorrect: %+v", tt.edition, got)
		}
	}
}

func TestWorldSortingAndFallbackDates(t *testing.T) {
	// Discovery also searches normal launcher roots. Isolate the fixture from
	// real saves on developers' machines.
	t.Setenv("APPDATA", "")
	t.Setenv("LOCALAPPDATA", "")
	t.Setenv("USERPROFILE", "")
	root := t.TempDir()
	older := filepath.Join(root, "Older")
	newer := filepath.Join(root, "Newer")
	writeFixtureWorld(t, older, javaEdition, "Older World", 1700000000)
	writeFixtureWorld(t, newer, javaEdition, "Newer World", 1750000000)
	found := discoverWorlds(javaEdition, root)
	if len(found) != 2 || found[0].name != "Newer World" || found[1].name != "Older World" || !found[0].exactDate {
		t.Fatalf("unexpected sorted worlds: %+v", found)
	}
	// Corrupted metadata must not crash discovery or be misreported as an exact date.
	if err := os.WriteFile(filepath.Join(newer, "level.dat"), []byte("not compressed NBT"), 0644); err != nil {
		t.Fatal(err)
	}
	modtime := time.Unix(1800000000, 0)
	if err := os.Chtimes(filepath.Join(newer, "level.dat"), modtime, modtime); err != nil {
		t.Fatal(err)
	}
	found = discoverWorlds(javaEdition, root)
	if len(found) != 2 || found[0].exactDate || found[0].played.Unix() != modtime.Unix() {
		t.Fatalf("metadata fallback incorrect: %+v", found)
	}
}

func TestMissingEnvironmentDoesNotScanRelativeFolders(t *testing.T) {
	t.Setenv("APPDATA", "")
	t.Setenv("LOCALAPPDATA", "")
	t.Setenv("USERPROFILE", "")
	for _, edition := range []worldEdition{javaEdition, bedrockEdition} {
		if roots := worldRoots(edition); len(roots) != 0 {
			t.Fatalf("%s generated unintended relative paths: %v", edition, roots)
		}
	}
}

func TestPlayerPositionFloorsNegativeCoordinates(t *testing.T) {
	for _, edition := range []worldEdition{javaEdition, bedrockEdition} {
		order := binary.ByteOrder(binary.LittleEndian)
		if edition == javaEdition {
			order = binary.BigEndian
		}
		base := fixtureNBT(order, "Negative coordinates", 1750000000, 10, 10)
		var nbt bytes.Buffer
		nbt.Write(base[:len(base)-1])
		nbt.WriteByte(10)
		_ = binary.Write(&nbt, order, uint16(len("Player")))
		nbt.WriteString("Player")
		nbt.WriteByte(9)
		_ = binary.Write(&nbt, order, uint16(len("Pos")))
		nbt.WriteString("Pos")
		nbt.WriteByte(6)
		_ = binary.Write(&nbt, order, int32(3))
		for _, coordinate := range []float64{-0.25, 70, -12.9} {
			_ = binary.Write(&nbt, order, coordinate)
		}
		nbt.WriteByte(0)
		nbt.WriteByte(0)

		var saved bytes.Buffer
		if edition == javaEdition {
			gz := gzip.NewWriter(&saved)
			if _, err := gz.Write(nbt.Bytes()); err != nil {
				t.Fatal(err)
			}
			if err := gz.Close(); err != nil {
				t.Fatal(err)
			}
		} else {
			_ = binary.Write(&saved, order, uint32(10))
			_ = binary.Write(&saved, order, uint32(nbt.Len()))
			saved.Write(nbt.Bytes())
		}
		path := filepath.Join(t.TempDir(), "level.dat")
		if err := os.WriteFile(path, saved.Bytes(), 0644); err != nil {
			t.Fatal(err)
		}
		got, err := readLevelDat(path, edition)
		if err != nil {
			t.Fatal(err)
		}
		if !got.HasCenter || got.X != -1 || got.Z != -13 {
			t.Fatalf("%s player position should round toward negative infinity: %+v", edition, got)
		}
	}
}

func TestOverlappingLauncherRootsPreserveSingleWorld(t *testing.T) {
	root := t.TempDir()
	t.Setenv("APPDATA", root)
	t.Setenv("USERPROFILE", root)
	t.Setenv("LOCALAPPDATA", root)
	saves := filepath.Join(root, ".minecraft", "saves")
	world := filepath.Join(saves, "Example")
	writeFixtureWorld(t, world, javaEdition, "Overlapping root", 1750000000)
	found := discoverWorlds(javaEdition, saves)
	if len(found) != 1 || found[0].path != world || found[0].name != "Overlapping root" {
		t.Fatalf("overlapping launcher folders should produce one intact entry: %+v", found)
	}
}

func TestBedrockWorldNamePrecedenceAndFallback(t *testing.T) {
	dir := t.TempDir()
	writeFixtureWorld(t, dir, bedrockEdition, "NBT world title", 1750000000)
	levelname := filepath.Join(dir, "levelname.txt")
	if err := os.WriteFile(levelname, []byte("Fallback title"), 0644); err != nil {
		t.Fatal(err)
	}
	got := readWorldInfo(dir, bedrockEdition)
	if got.name != "NBT world title" {
		t.Fatalf("level.dat world title must take precedence: %+v", got)
	}
	// This fallback may be inaccessible while the game updates the file.
	// A complete, valid NBT name must not require opening it.
	if err := os.Remove(levelname); err != nil {
		t.Fatal(err)
	}
	if err := os.Mkdir(levelname, 0755); err != nil {
		t.Fatal(err)
	}
	if got := readWorldInfo(dir, bedrockEdition); got.name != "NBT world title" {
		t.Fatalf("levelname.txt was unnecessarily required: %+v", got)
	}
	if err := os.Remove(levelname); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(levelname, []byte("\ufeffFallback title\x00\x00"), 0644); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(dir, "level.dat"), []byte("invalid Bedrock NBT"), 0644); err != nil {
		t.Fatal(err)
	}
	got = readWorldInfo(dir, bedrockEdition)
	if got.name != "Fallback title" || got.exactDate {
		t.Fatalf("unreadable NBT must still use levelname.txt: %+v", got)
	}
	if err := os.Remove(levelname); err != nil {
		t.Fatal(err)
	}
	got = readWorldInfo(dir, bedrockEdition)
	if got.name != filepath.Base(dir) {
		t.Fatalf("both missing titles should use folder name: %+v", got)
	}
}

func TestNetherAndEndOnlyJavaWorlds(t *testing.T) {
	for _, dir := range []string{"DIM-1", "DIM1"} {
		path := filepath.Join(t.TempDir(), "world")
		writeFixtureWorld(t, path, javaEdition, "Dimension-only", 1750000000)
		if err := os.Remove(filepath.Join(path, "region")); err != nil {
			t.Fatal(err)
		}
		if err := os.MkdirAll(filepath.Join(path, dir, "region"), 0755); err != nil {
			t.Fatal(err)
		}
		if !validWorldDir(path, javaEdition) {
			t.Fatalf("Java world containing only %s should remain selectable", dir)
		}
	}
}
