package main

import (
	"os"
	"path/filepath"
	"strings"
)

// Where the user's chosen project root is remembered between launches, so
// they only need to point the app at the repo once.
func configFilePath() (string, error) {
	dir, err := os.UserConfigDir()
	if err != nil {
		return "", err
	}
	appDir := filepath.Join(dir, "meridian-desktop")
	if err := os.MkdirAll(appDir, 0o755); err != nil {
		return "", err
	}
	return filepath.Join(appDir, "project-root.txt"), nil
}

func loadSavedProjectRoot() string {
	path, err := configFilePath()
	if err != nil {
		return ""
	}
	data, err := os.ReadFile(path)
	if err != nil {
		return ""
	}
	return strings.TrimSpace(string(data))
}

func saveProjectRoot(root string) error {
	path, err := configFilePath()
	if err != nil {
		return err
	}
	return os.WriteFile(path, []byte(root), 0o644)
}
