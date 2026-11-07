package main

import (
	"encoding/json"
	"os"
	"regexp"
	"strings"
	"testing"
)

func TestReleaseVersionMatchesBuildAndDocumentation(t *testing.T) {
	version := appVersion()
	if !regexp.MustCompile(`^[0-9]+\.[0-9]+\.[0-9]+$`).MatchString(version) {
		t.Fatalf("invalid release version %q", version)
	}
	// Public release names may omit a trailing .0; the executable keeps a
	// standard three-part package version and four-part Windows file version.
	release := strings.TrimSuffix(version, ".0")
	cases := []struct {
		path string
		want string
	}{
		{".github/workflows/build.yml", "--title \"Release " + release + "\""},
		{".github/workflows/build.yml", "refs/tags/release-" + release + "-"},
		{".github/workflows/build.yml", "--notes-file .github/RELEASE_NOTES_v" + release + ".md"},
		{"README.md", "**Version:** v" + release},
		{".github/RELEASE_NOTES_v" + release + ".md", "# Release " + release},
	}
	for _, tc := range cases {
		data, err := os.ReadFile(tc.path)
		if err != nil {
			t.Fatal(err)
		}
		if !strings.Contains(string(data), tc.want) {
			t.Errorf("%s does not contain %q; update VERSION and release metadata together", tc.path, tc.want)
		}
	}
}

func TestWindowsExeVersionMetadata(t *testing.T) {
	data, err := os.ReadFile("winres/winres.json")
	if err != nil {
		t.Fatal(err)
	}
	var manifest struct {
		Version map[string]map[string]struct {
			Fixed struct {
				FileVersion    string `json:"file_version"`
				ProductVersion string `json:"product_version"`
			} `json:"fixed"`
			Info map[string]map[string]string `json:"info"`
		} `json:"RT_VERSION"`
	}
	if err := json.Unmarshal(data, &manifest); err != nil {
		t.Fatal(err)
	}
	win, ok := manifest.Version["#1"]["0000"]
	if !ok {
		t.Fatal("missing Windows VERSIONINFO resource")
	}
	want := appVersion() + ".0"
	if win.Fixed.FileVersion != want || win.Fixed.ProductVersion != want ||
		win.Info["0409"]["FileVersion"] != want || win.Info["0409"]["ProductVersion"] != want {
		t.Fatalf("Windows file/product version disagrees with VERSION %s: %+v", want, win)
	}
	manifestData, err := os.ReadFile("winres/app.manifest")
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(string(manifestData), `version="`+want+`"`) {
		t.Fatalf("winres/app.manifest version does not match VERSION %s: %s", want, string(manifestData))
	}
}
