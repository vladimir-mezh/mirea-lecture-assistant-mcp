package installation

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

func TestOnlyMatchingInstalledAdapterCanBeSelected(t *testing.T) {
	root := t.TempDir()
	folder := filepath.Join(root, "versions", "0.2.1")
	if err := os.MkdirAll(folder, 0700); err != nil {
		t.Fatal(err)
	}
	path := filepath.Join(folder, "MireaAssistantMcp.exe")
	data := []byte("fixture executable, never run")
	os.WriteFile(path, data, 0600)
	digest := sha256.Sum256(data)
	for _, version := range []string{"../outside", `..\outside`, "", "0.2.1"} {
		manifest, _ := json.Marshal(map[string]any{"version": version, "app_protocol": 1,
			"sha256": map[string]string{"MireaAssistantMcp.exe": hex.EncodeToString(digest[:])}})
		os.WriteFile(filepath.Join(root, "current.json"), manifest, 0600)
		selected, err := Select(root)
		if version == "0.2.1" {
			if err != nil || selected != path {
				t.Fatal("valid adapter rejected")
			}
		} else if err == nil {
			t.Fatal("traversal accepted")
		}
	}
	os.WriteFile(path, []byte("modified"), 0600)
	if _, err := Select(root); err != ErrInstall {
		t.Fatal("modified adapter accepted")
	}
}
