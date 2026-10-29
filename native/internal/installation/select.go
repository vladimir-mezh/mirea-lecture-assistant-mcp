// Package installation selects only a hash-verified, installed adapter.
package installation

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io"
	"os"
	"path/filepath"
	"regexp"
	"strings"
)

var versionPattern = regexp.MustCompile(`^\d+\.\d+\.\d+$`)
var ErrInstall = errors.New("MCP is not installed or its integrity check failed; reinstall from Lecture Assistant's MCP tab.")

func Select(root string) (string, error) {
	file, err := os.Open(filepath.Join(root, "current.json"))
	if err != nil {
		return "", ErrInstall
	}
	defer file.Close()
	data, err := io.ReadAll(io.LimitReader(file, 65537))
	if err != nil || len(data) > 65536 {
		return "", ErrInstall
	}
	var manifest struct {
		Version  string            `json:"version"`
		Protocol int               `json:"app_protocol"`
		Hashes   map[string]string `json:"sha256"`
	}
	if json.Unmarshal(data, &manifest) != nil || !versionPattern.MatchString(manifest.Version) || manifest.Protocol != 1 {
		return "", ErrInstall
	}
	expected := manifest.Hashes["MireaAssistantMcp.exe"]
	if decoded, err := hex.DecodeString(expected); err != nil || len(decoded) != sha256.Size {
		return "", ErrInstall
	}
	selected := filepath.Join(root, "versions", manifest.Version, "MireaAssistantMcp.exe")
	adapter, err := os.Open(selected)
	if err != nil {
		return "", ErrInstall
	}
	defer adapter.Close()
	info, err := adapter.Stat()
	if err != nil || !info.Mode().IsRegular() || info.Size() > 80*1024*1024 {
		return "", ErrInstall
	}
	hash := sha256.New()
	if _, err := io.Copy(hash, adapter); err != nil || !strings.EqualFold(hex.EncodeToString(hash.Sum(nil)), expected) {
		return "", ErrInstall
	}
	return selected, nil
}
