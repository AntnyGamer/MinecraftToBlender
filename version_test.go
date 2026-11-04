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
	cases := []struct {
		path string
		want string
	}{
		{".github/workflows/build.yml", "gh release create v" + version + " "},
		{".github/workflows/build.yml", "--notes-file .github/RELEASE_NOTES_v" + version + ".md"},
		{"README.md", "**Version:** v" + version},
		{".github/RELEASE_NOTES_v" + version + ".md", "# MinecraftToBlender v" + version},
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
}
