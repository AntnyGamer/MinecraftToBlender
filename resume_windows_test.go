//go:build windows

package main

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"testing"
)

func TestResumeCheckpointRequiresIdenticalFilesAndSettings(t *testing.T) {
	base:=t.TempDir()
	world:=filepath.Join(base,"world")
	out:=filepath.Join(base,"exports","Saved","Saved.usd")
	if err:=os.MkdirAll(filepath.Join(world,"db"),0700);err!=nil {t.Fatal(err)}
	if err:=os.MkdirAll(filepath.Join(filepath.Dir(out),"Saved_chunks"),0700);err!=nil {t.Fatal(err)}
	write:=func(name,content string) {
		t.Helper()
		if err:=os.WriteFile(name,[]byte(content),0600);err!=nil{t.Fatal(err)}
	}
	write(filepath.Join(world,"level.dat"),"world data")
	write(filepath.Join(world,"db","CURRENT"),"MANIFEST-00001")
	write(out,"#usda 1.0")
	write(filepath.Join(filepath.Dir(out),"Saved_materials.json"),"{}")
	write(filepath.Join(filepath.Dir(out),"Saved_chunks","region_1_chunk_1_1.usd"),"def Mesh \"terrain\" {}")
	opt:=exportOptions{Dimension:"overworld",Frames:true,Paintings:true}
	key:=makeResumeIdentity(world,bedrockEdition,"Saved",opt,512,0,0,-64,319,false)
	checkpoint:=filepath.Join(base,"checkpoint.json")
	if err:=saveResumeCheckpoint(context.Background(),checkpoint,key,world,out);err!=nil{t.Fatal(err)}
	if !verifiedResumeCheckpoint(context.Background(),checkpoint,key,world,out) {t.Fatal("verified identical export should resume")}
	// Blender writes its log into the USD folder even on a failed import.
	// Incomplete .blend files and backups must not invalidate the USD checkpoint.
	write(filepath.Join(filepath.Dir(out),"Minecraft_Blender_Import.log"),"Blender exited before confirmation")
	write(filepath.Join(filepath.Dir(out),"Saved.blend"),"partial blend output")
	write(filepath.Join(filepath.Dir(out),"Saved_2.blend"),"another failed attempt")
	write(filepath.Join(filepath.Dir(out),"Saved.blend1"),"backup")
	write(filepath.Join(filepath.Dir(out),"Saved_texture_audit.txt"),"generated Blender texture diagnostics")
	write(filepath.Join(filepath.Dir(out),"Saved_2_texture_audit.txt"),"generated retry diagnostics")
	if !verifiedResumeCheckpoint(context.Background(),checkpoint,key,world,out) {
		t.Fatal("Blender log/project files incorrectly invalidate a complete USD export")
	}
	write(filepath.Join(filepath.Dir(out),"Saved_materials.json"),"{\"modified\":true}")
	if verifiedResumeCheckpoint(context.Background(),checkpoint,key,world,out) {
		t.Fatal("changed material metadata was ignored")
	}
	write(filepath.Join(filepath.Dir(out),"Saved_materials.json"),"{}")
	write(filepath.Join(world,"level.dat"),"new data  ")
	if verifiedResumeCheckpoint(context.Background(),checkpoint,key,world,out) {t.Fatal("changed source world accepted")}
	write(filepath.Join(world,"level.dat"),"world data")
	write(out,"#usda 2.0")
	if verifiedResumeCheckpoint(context.Background(),checkpoint,key,world,out) {t.Fatal("changed USD accepted")}
	write(out,"#usda 1.0")
	changed:=key
	changed.Dimension="the_nether"
	if verifiedResumeCheckpoint(context.Background(),checkpoint,changed,world,out) {t.Fatal("changed dimension accepted")}
}

func TestResumeHashStopsImmediatelyOnCancellation(t *testing.T) {
	world:=filepath.Join(t.TempDir(),"world")
	if err:=os.MkdirAll(world,0700);err!=nil{t.Fatal(err)}
	if err:=os.WriteFile(filepath.Join(world,"level.dat"),[]byte("snapshot"),0600);err!=nil{t.Fatal(err)}
	ctx,cancel:=context.WithCancel(context.Background())
	cancel()
	_,err:=digestDirectory(ctx,world)
	if !errors.Is(err,context.Canceled){
		t.Fatalf("cancelled digest must return context.Canceled, got: %v",err)
	}
	identity:=makeResumeIdentity(world,bedrockEdition,"Example",exportOptions{Dimension:"overworld"},16,0,0,0,128,false)
	if err:=saveResumeCheckpoint(ctx,filepath.Join(t.TempDir(),"resume.json"),identity,world,world);!errors.Is(err,context.Canceled){
		t.Fatalf("cancelled checkpoint save must stop, got: %v",err)
	}
}
