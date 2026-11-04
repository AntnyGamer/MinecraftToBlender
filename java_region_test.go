package main

import (
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
	present,err:=javaRegionHasSavedChunks(root,"overworld",16,-8,8)
	if err!=nil||!present {t.Fatalf("expected saved negative-X chunk: %v, %v",present,err)}
	present,err=javaRegionHasSavedChunks(root,"overworld",16,1000,1000)
	if err!=nil||present {t.Fatalf("wrong area reported saved: %v, %v",present,err)}
	if floorBlockDiv(-1,32)!=-1||floorBlockDiv(-33,32)!=-2||floorBlockDiv(0,32)!=0 {
		t.Fatal("negative Minecraft region rounding is incorrect")
	}
}
