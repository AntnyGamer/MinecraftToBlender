package main

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"testing"
)

func TestJavaRegionHeaderProbeHandlesNegativeWorldCoordinates(t *testing.T) {
	root:=t.TempDir()
	regions:=filepath.Join(root,"region")
	if err:=os.MkdirAll(regions,0700);err!=nil {t.Fatal(err)}
	header:=make([]byte,4096)
	offset:=4*31 // chunk X=-1, Z=0 within r.-1.0.mca
	header[offset+2]=2
	header[offset+3]=1
	if err:=os.WriteFile(filepath.Join(regions,"r.-1.0.mca"),header,0600);err!=nil{t.Fatal(err)}
	present,err:=javaRegionHasSavedChunksContext(context.Background(),root,"overworld",16,-8,8)
	if err!=nil||!present {t.Fatalf("expected saved negative-X chunk: %v, %v",present,err)}
	present,err=javaRegionHasSavedChunksContext(context.Background(),root,"overworld",16,1000,1000)
	if err!=nil||present {t.Fatalf("wrong area reported saved: %v, %v",present,err)}
	if floorBlockDiv(-1,32)!=-1||floorBlockDiv(-33,32)!=-2||floorBlockDiv(0,32)!=0 {
		t.Fatal("negative Minecraft region rounding is incorrect")
	}
}

func TestJavaRegionInspectionHonorsCancel(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	_, err := javaRegionHasSavedChunksContext(ctx, t.TempDir(), "overworld", 8192, 0, 0)
	if !errors.Is(err, context.Canceled) {
		t.Fatalf("canceled region scan must immediately stop: %v", err)
	}
}

func TestJavaDimensionRegionPaths(t *testing.T) {
	root := t.TempDir()
	for dimension, want := range map[string]string{
		"overworld": filepath.Join(root, "region"),
		"the_nether": filepath.Join(root, "DIM-1", "region"),
		"the_end": filepath.Join(root, "DIM1", "region"),
	} {
		got, err := javaDimensionRegionPath(root, dimension)
		if err != nil || got != want {
			t.Fatalf("dimension %s: got %q, %v, want %q", dimension, got, err, want)
		}
	}
	if _, err := javaDimensionRegionPath(root, "unknown"); err == nil {
		t.Fatal("unknown Java dimensions should be rejected")
	}
}
