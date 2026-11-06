package main

import (
	"context"
	"image"
	imgcolor "image/color"
	"image/png"
	"os"
	"path/filepath"
	"testing"
)

func TestPreviewCoordinatesRequireExplicitMapHit(t *testing.T) {
	for _, sample := range []struct{ x, y, wantX, wantZ int; inside bool }{
		{32,70,-508,-982,true},
		{543,581,514,40,true},
		{288,326,4,-470,true},
		{31,70,0,0,false},
		{32,69,0,0,false},
		{544,581,0,0,false},
		{543,582,0,0,false},
	} {
		x,z,inside := previewCoordinates(-508,-982,1024,sample.x,sample.y)
		if inside!=sample.inside || (inside&&(x!=sample.wantX||z!=sample.wantZ)) {
			t.Fatalf("hover (%d,%d) -> (%d,%d,%t), expected (%d,%d,%t)",
				sample.x,sample.y,x,z,inside,sample.wantX,sample.wantZ,sample.inside)
		}
	}
}

func TestPreviewMapLayoutAlwaysReservesCoordinateFooter(t *testing.T) {
	for _, viewport := range []struct{width, height, expectedSide int}{
		{580,660,512},
		{580,630,480},
		{400,500,336},
		{340,410,260},
	} {
		left, top, side := previewMapLayout(viewport.width, viewport.height)
		if side != viewport.expectedSide || left < 0 || left+side > viewport.width {
			t.Fatalf("map layout %dx%d produced (%d,%d,%d)", viewport.width, viewport.height, left, top, side)
		}
		if top+side+66 > viewport.height {
			t.Fatalf("coordinate footer clipped below %dx%d client at Y=%d",
				viewport.width, viewport.height, top+side+66)
		}
	}
}

func TestPreviewCoordinatesMatchScaledPreviewMap(t *testing.T) {
	left,top,side:=previewMapLayout(580,630)
	for _, sample:=range []struct{x,y,wantX,wantZ int; hit bool}{
		{left,top,-508,-982,true},
		{left+side/2,top+side/2,4,-470,true},
		{left+side-1,top+side-1,513,39,true},
		{left-1,top,0,0,false},
		{left,top+side,0,0,false},
	} {
		x,z,ok:=previewCoordinatesInMap(-508,-982,1024,sample.x,sample.y,left,top,side)
		if ok!=sample.hit || (ok&&(x!=sample.wantX||z!=sample.wantZ)) {
			t.Fatalf("scaled preview hit (%d,%d) -> (%d,%d,%t), want (%d,%d,%t)",
				sample.x,sample.y,x,z,ok,sample.wantX,sample.wantZ,sample.hit)
		}
	}
}

func TestPreviewCacheKeyIncludesEveryPreviewChoice(t *testing.T) {
	base := previewCacheKey("C:/world","bedrock","overworld",false,1024,0,0,"1.1.2","unchanged")
	for _, changed := range []string{
		previewCacheKey("C:/other","bedrock","overworld",false,1024,0,0,"1.1.2","unchanged"),
		previewCacheKey("C:/world","java","overworld",false,1024,0,0,"1.1.2","unchanged"),
		previewCacheKey("C:/world","bedrock","nether",false,1024,0,0,"1.1.2","unchanged"),
		previewCacheKey("C:/world","bedrock","overworld",true,1024,0,0,"1.1.2","unchanged"),
		previewCacheKey("C:/world","bedrock","overworld",false,512,0,0,"1.1.2","unchanged"),
		previewCacheKey("C:/world","bedrock","overworld",false,1024,1,0,"1.1.2","unchanged"),
		previewCacheKey("C:/world","bedrock","overworld",false,1024,0,1,"1.1.2","unchanged"),
		previewCacheKey("C:/world","bedrock","overworld",false,1024,0,0,"1.1.3","unchanged"),
		previewCacheKey("C:/world","bedrock","overworld",false,1024,0,0,"1.1.2","changed"),
	} {
		if changed==base { t.Fatal("cache key ignored a preview input") }
	}
}

func TestPreviewFingerprintTracksBedrockDBChanges(t *testing.T) {
	world := t.TempDir()
	db := filepath.Join(world,"db")
	if err:=os.Mkdir(db,0700);err!=nil {t.Fatal(err)}
	level:=filepath.Join(world,"level.dat")
	data:=filepath.Join(db,"000001.ldb")
	for _, path := range []string{level,data} {
		if err:=os.WriteFile(path,[]byte("initial"),0600);err!=nil {t.Fatal(err)}
	}
	original,err:=previewWorldFingerprint(context.Background(),world)
	if err!=nil {t.Fatal(err)}
	same,err:=previewWorldFingerprint(context.Background(),world)
	if err!=nil || same!=original {t.Fatalf("unchanged fingerprint: %q %v",same,err)}
	if err:=os.WriteFile(data,[]byte("new chunk saved"),0600);err!=nil {t.Fatal(err)}
	next,err:=previewWorldFingerprint(context.Background(),world)
	if err!=nil || next==original {t.Fatalf("DB mutation did not invalidate preview: %v",err)}
	if err:=os.WriteFile(level,[]byte("different metadata"),0600);err!=nil {t.Fatal(err)}
	after,err:=previewWorldFingerprint(context.Background(),world)
	if err!=nil || after==next {t.Fatalf("metadata mutation did not invalidate preview: %v",err)}
	ctx,cancel:=context.WithCancel(context.Background())
	cancel()
	if _,err:=previewWorldFingerprint(ctx,world);err==nil {t.Fatal("fingerprint ignored cancellation")}
}

func TestPreviewCacheCopiesWithoutDeletingSharedPng(t *testing.T) {
	dir:=t.TempDir()
	cacheDir:=filepath.Join(dir,"cache")
	if err:=os.Mkdir(cacheDir,0700);err!=nil{t.Fatal(err)}
	original:=filepath.Join(dir,"original.png")
	f,err:=os.Create(original)
	if err!=nil{t.Fatal(err)}
	img:=image.NewRGBA(image.Rect(0,0,256,256))
	img.Set(0,0,imgcolor.RGBA{R:123,G:45,B:67,A:255})
	if err:=png.Encode(f,img);err!=nil{t.Fatal(err)}
	if err:=f.Close();err!=nil{t.Fatal(err)}
	if err:=storePreviewCache(original,cacheDir,"stable");err!=nil{t.Fatal(err)}
	cached:=filepath.Join(cacheDir,"stable.png")
	first,ok:=cachedPreview(cached,dir)
	if !ok || first==cached {t.Fatal("cache failed or returned the shared file")}
	if err:=os.Remove(first);err!=nil{t.Fatal(err)}
	second,ok:=cachedPreview(cached,dir)
	if !ok || second==first {t.Fatal("closing preview deleted cached image")}
	_ = os.Remove(second)
	if err:=os.WriteFile(cached,[]byte("not a PNG"),0600);err!=nil{t.Fatal(err)}
	if _,ok:=cachedPreview(cached,dir);ok {t.Fatal("accepted corrupted preview")}
	if _,err:=os.Stat(cached);!os.IsNotExist(err) {t.Fatalf("invalid cache entry not cleared: %v",err)}
	if err:=storePreviewCache(original,cacheDir,"stable");err!=nil{t.Fatalf("replacing corrupt cached image: %v",err)}
	repaired,ok:=cachedPreview(cached,dir)
	if !ok {t.Fatal("could not read repaired cache")}
	_ = os.Remove(repaired)
}
