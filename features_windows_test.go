//go:build windows

package main

import "testing"

func TestJavaMajorVersion(t *testing.T) {
	cases:=map[string]int {
		`openjdk version "21.0.5" 2024-10-15`:21,
		`java version "1.8.0_421"`:8,
		`openjdk version "25" 2025-09-16`:25,
		`unrecognized Java output`:0,
	}
	for text,want:=range cases {
		if got:=javaMajorVersion(text);got!=want {
			t.Fatalf("%s: got Java %d, want %d",text,got,want)
		}
	}
}
