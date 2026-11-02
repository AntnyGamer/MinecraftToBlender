package main

// worldCenterOutsideRegion checks a saved player/spawn coordinate against
// exactly the inclusive region MiEx will export, including even sizes.
func worldCenterOutsideRegion(centerX, centerZ, size, savedX, savedZ int) bool {
	if size <= 0 {
		return false
	}
	minX, minZ := centerX-size/2, centerZ-size/2
	return savedX < minX || savedX >= minX+size || savedZ < minZ || savedZ >= minZ+size
}
