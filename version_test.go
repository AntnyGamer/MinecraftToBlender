package main

import (
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
