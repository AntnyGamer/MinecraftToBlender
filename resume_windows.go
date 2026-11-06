//go:build windows

package main

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"io/fs"
	"os"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
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
	PipelineHash string
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
		PipelineHash:resumePipelineHash(payload),
	}
}

func resumePipelineHash(assets fs.FS) string {
	hasher := sha256.New()
	entries, err := fs.ReadDir(assets, "assets")
	if err != nil { return "" }
	for _, entry := range entries {
		if entry.IsDir() { continue }
		// Blender display/import changes can reuse the same verified USD.
		// Only export/model/texture assets invalidate expensive Minecraft work.
		if entry.Name() != "Export_World.ps1" && entry.Name() != "Convert_USD_To_Crate.py" &&
			!strings.HasPrefix(entry.Name(), "Bedrock_") && !strings.HasPrefix(entry.Name(), "Java_") { continue }
		data, err := fs.ReadFile(assets, "assets/" + entry.Name())
		if err != nil { return "" }
		_, _ = fmt.Fprintf(hasher, "%s\x00%d\x00", entry.Name(), len(data))
		_, _ = hasher.Write(data)
	}
	return hex.EncodeToString(hasher.Sum(nil))
}

// Calculate an exact digest before reusing work. File sizes or timestamps
// alone cannot establish that a Minecraft LevelDB snapshot stayed unchanged.
type cancelReader struct {
	ctx context.Context
	reader io.Reader
}

func (r cancelReader) Read(p []byte) (int, error) {
	if err := r.ctx.Err(); err != nil { return 0, err }
	return r.reader.Read(p)
}

func digestDirectory(ctx context.Context, root string) (string,error) {
	return digestDirectoryFiltered(ctx, root, nil)
}

var blenderProjectName = regexp.MustCompile(`(?i)\.blend[0-9]*$`)
var blenderTextureAuditName = regexp.MustCompile(`(?i)_texture_audit\.txt$`)

func isImportGeneratedFile(rel string) bool {
	// Ignore only Blender-created root files; keep hashing every USD sidecar,
	// material, texture, and chunk layer used by the importer.
	if filepath.Dir(rel) != "." { return false }
	name := filepath.Base(rel)
	return strings.EqualFold(name, "Minecraft_Blender_Import.log") || blenderProjectName.MatchString(name) || blenderTextureAuditName.MatchString(name)
}

func digestExportDirectory(ctx context.Context, root string) (string,error) {
	return digestDirectoryFiltered(ctx, root, isImportGeneratedFile)
}

func digestDirectoryFiltered(ctx context.Context, root string, exclude func(string) bool) (string,error) {
	hasher:=sha256.New()
	buffer:=make([]byte,128*1024)
	err:=filepath.WalkDir(root,func(path string,d os.DirEntry,walkErr error)error{
		if err := ctx.Err(); err != nil { return err }
		if walkErr!=nil{return walkErr}
		if d.IsDir(){return nil}
		if d.Type()&os.ModeSymlink!=0 {return fmt.Errorf("cannot reuse a checkpoint with symlinks: %s",path)}
		if !d.Type().IsRegular(){return fmt.Errorf("unexpected non-file in checkpoint: %s",path)}
		rel,err:=filepath.Rel(root,path);if err!=nil{return err}
		if exclude != nil && exclude(rel) { return nil }
		info,err:=d.Info();if err!=nil{return err}
		_,_=fmt.Fprintf(hasher,"%s\x00%d\x00",filepath.ToSlash(rel),info.Size())
		f,err:=os.Open(path);if err!=nil{return err}
		_,err=io.CopyBuffer(hasher,cancelReader{ctx:ctx,reader:f},buffer)
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

func saveResumeCheckpoint(ctx context.Context,path string,identity resumeIdentity,worldPath,usdPath string)error{
	worldHash,err:=digestDirectory(ctx,worldPath);if err!=nil{return err}
	exportHash,err:=digestExportDirectory(ctx,filepath.Dir(usdPath));if err!=nil{return err}
	if err:=ctx.Err();err!=nil{return err}
	data,err:=json.MarshalIndent(resumeCheckpoint{Identity:identity,WorldHash:worldHash,ExportHash:exportHash},"","  ")
	if err!=nil{return err}
	if err:=os.MkdirAll(filepath.Dir(path),0700);err!=nil{return err}
	temp:=path+".tmp"+strconv.FormatInt(int64(os.Getpid()),10)
	if err:=os.WriteFile(temp,data,0600);err!=nil{return err}
	if err:=os.Rename(temp,path);err!=nil{_ =os.Remove(temp);return err}
	return nil
}

func verifiedResumeCheckpoint(ctx context.Context,path string,identity resumeIdentity,worldPath,usdPath string) bool{
	if identity.PipelineHash == "" { return false }
	data,err:=os.ReadFile(path);if err!=nil{return false}
	var saved resumeCheckpoint
	if json.Unmarshal(data,&saved)!=nil||saved.Identity!=identity||saved.WorldHash==""||saved.ExportHash==""{return false}
	if usdFiles(usdPath)!=nil{return false}
	worldHash,err:=digestDirectory(ctx,worldPath)
	if err!=nil||worldHash!=saved.WorldHash{return false}
	exportHash,err:=digestExportDirectory(ctx,filepath.Dir(usdPath))
	return err==nil&&exportHash==saved.ExportHash
}

