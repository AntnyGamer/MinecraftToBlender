package main

import (
	_ "embed"
	"strings"
)

//go:embed VERSION
var embeddedVersion string

func appVersion() string {
	return strings.TrimSpace(embeddedVersion)
}
