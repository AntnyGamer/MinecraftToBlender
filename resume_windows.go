//go:build windows

package main

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"hash"
	"io"
	"os"
	"path/filepath"
	"strconv"
)

type resumeIdentity struct {
	WorldPath string
	Edition string
	ExportName string
	Dimension string
	Size, X, Z, MinY, MaxY int
	WorldPacks bool
	Entities string
	AppVersion string
}

type resumeCheckpoint struct {
	Identity resumeIdentity
	WorldHash string
	ExportHash string
}

func makeResumeIdentity(world string,edition worldEdition,name string,options exportOptions,size,x,z,minY,maxY int,worldPacks bool) resumeIdentity {
	full,err:=filepath.Abs(world)
	if err!=nil {full=world}
	return resumeIdentity{
		WorldPath:filepath.Clean(full),Edition:string(edition),ExportName:name,
		Dimension:options.Dimension,Size:size,X:x,Z:z,MinY:minY,MaxY:maxY,
		WorldPacks:worldPacks,Entities:options.EntityList(),AppVersion:appVersion(),
	}
}

// Calculate an exact digest before reusing work. File sizes or timestamps
// alone cannot establish that a Minecraft LevelDB snapshot stayed unchanged.
func digestDirectory(root string) (string,error) {
	hasher:=sha256.New()
	buffer:=make([]byte,128*1024)
	err:=filepath.WalkDir(root,func(path string,d os.DirEntry,walkErr error)error{
		if walkErr!=nil{return walkErr}
		if d.IsDir(){return nil}
		if d.Type()&os.ModeSymlink!=0 {return fmt.Errorf("cannot reuse a checkpoint with symlinks: %s",path)}
		if !d.Type().IsRegular(){return fmt.Errorf("unexpected non-file in checkpoint: %s",path)}
		rel,err:=filepath.Rel(root,path);if err!=nil{return err}
		info,err:=d.Info();if err!=nil{return err}
		_,_=fmt.Fprintf(hasher,"%s\x00%d\x00",filepath.ToSlash(rel),info.Size())
		f,err:=os.Open(path);if err!=nil{return err}
		_,err=io.CopyBuffer(hasher,f,buffer)
		closeErr:=f.Close()
		if err!=nil{return err}
		return closeErr
	})
	if err!=nil{return "",err}
	return hex.EncodeToString(hasher.Sum(nil)),nil
}

func checkpointFile(workspace,name string) string {
	return filepath.Join(workspace,"AppTools","MiEx_Work","checkpoints",name+".json")
}

func saveResumeCheckpoint(path string,identity resumeIdentity,worldPath,usdPath string)error{
	worldHash,err:=digestDirectory(worldPath);if err!=nil{return err}
	exportHash,err:=digestDirectory(filepath.Dir(usdPath));if err!=nil{return err}
	data,err:=json.MarshalIndent(resumeCheckpoint{Identity:identity,WorldHash:worldHash,ExportHash:exportHash},"","  ")
	if err!=nil{return err}
	if err:=os.MkdirAll(filepath.Dir(path),0700);err!=nil{return err}
	temp:=path+".tmp"+strconv.FormatInt(int64(os.Getpid()),10)
	if err:=os.WriteFile(temp,data,0600);err!=nil{return err}
	if err:=os.Rename(temp,path);err!=nil{_ =os.Remove(temp);return err}
	return nil
}

func verifiedResumeCheckpoint(path string,identity resumeIdentity,worldPath,usdPath string) bool{
	data,err:=os.ReadFile(path);if err!=nil{return false}
	var saved resumeCheckpoint
	if json.Unmarshal(data,&saved)!=nil||saved.Identity!=identity||saved.WorldHash==""||saved.ExportHash==""{return false}
	if usdFiles(usdPath)!=nil{return false}
	worldHash,err:=digestDirectory(worldPath)
	if err!=nil||worldHash!=saved.WorldHash{return false}
	exportHash,err:=digestDirectory(filepath.Dir(usdPath))
	return err==nil&&exportHash==saved.ExportHash
}

var _ hash.Hash = sha256.New()
