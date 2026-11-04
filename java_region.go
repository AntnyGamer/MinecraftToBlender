package main

import (
	"context"
	"fmt"
	"io"
	"os"
	"path/filepath"
)

// floorBlockDiv handles negative Minecraft coordinates (Go integer division
// truncates toward zero, which would select the wrong region in the Nether).
func floorBlockDiv(n, divisor int) int {
	q := n / divisor
	if n < 0 && n%divisor != 0 { q-- }
	return q
}

// javaRegionHasSavedChunks inspects only 4 KiB Anvil headers, not entire
// chunk payloads. It never opens a world for writing. This indicates saved
// data exists, not whether MiEx can decode its block models.
func javaRegionHasSavedChunks(worldPath, dimension string, size, centerX, centerZ int) (bool,error) {
	return javaRegionHasSavedChunksContext(context.Background(), worldPath, dimension, size, centerX, centerZ)
}

func javaRegionHasSavedChunksContext(ctx context.Context, worldPath, dimension string, size, centerX, centerZ int) (bool,error) {
	if err:=ctx.Err();err!=nil {return false,err}
	folder:=worldPath
	switch dimension {
	case "overworld":
	case "the_nether":
		folder=filepath.Join(folder,"DIM-1")
	case "the_end":
		folder=filepath.Join(folder,"DIM1")
	default:
		return false,fmt.Errorf("unsupported dimension %q",dimension)
	}
	folder=filepath.Join(folder,"region")
	minX,minZ:=centerX-size/2,centerZ-size/2
	minCX,maxCX:=floorBlockDiv(minX,16),floorBlockDiv(minX+size-1,16)
	minCZ,maxCZ:=floorBlockDiv(minZ,16),floorBlockDiv(minZ+size-1,16)
	for rx:=floorBlockDiv(minCX,32);rx<=floorBlockDiv(maxCX,32);rx++ {
		for rz:=floorBlockDiv(minCZ,32);rz<=floorBlockDiv(maxCZ,32);rz++ {
			if err:=ctx.Err();err!=nil {return false,err}
			path:=filepath.Join(folder,fmt.Sprintf("r.%d.%d.mca",rx,rz))
			f,err:=os.Open(path)
			if os.IsNotExist(err){continue}
			if err!=nil {return false,err}
			var header [4096]byte
			_,readErr:=io.ReadFull(f,header[:])
			closeErr:=f.Close()
			if readErr!=nil{return false,fmt.Errorf("invalid Anvil region header %s: %w",path,readErr)}
			if closeErr!=nil{return false,closeErr}
			for cx:=max(minCX,rx*32);cx<=min(maxCX,rx*32+31);cx++ {
				if err:=ctx.Err();err!=nil {return false,err}
				for cz:=max(minCZ,rz*32);cz<=min(maxCZ,rz*32+31);cz++ {
					i:=4*((cx-rx*32)+(cz-rz*32)*32)
					if (header[i]!=0||header[i+1]!=0||header[i+2]!=0)&&header[i+3]!=0 {
						return true,nil
					}
				}
			}
		}
	}
	return false,nil
}
