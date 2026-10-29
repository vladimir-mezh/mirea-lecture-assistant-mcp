package adapter

import (
	"context"
	"encoding/json"
	"net"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func pairing(t *testing.T, profile string, server *httptest.Server) {
	t.Helper()
	_, portText, _ := net.SplitHostPort(server.Listener.Addr().String())
	var port int
	json.Unmarshal([]byte(portText), &port)
	data, _ := json.Marshal(map[string]any{"protocol": 1, "port": port, "token": strings.Repeat("fixture", 6)})
	if err := os.WriteFile(filepath.Join(profile, "mcp-connection.json"), data, 0600); err != nil {
		t.Fatal(err)
	}
}

func TestPairingIsRereadAndTrafficNeverUsesProxy(t *testing.T) {
	proxy := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { t.Error("pairing key sent to proxy"); w.WriteHeader(500) }))
	defer proxy.Close()
	t.Setenv("HTTP_PROXY", proxy.URL)
	profile := t.TempDir()
	backend, _ := NewBackend(profile, "Fixture")
	if backend.http.Transport.(*http.Transport).Proxy != nil {
		t.Fatal("environment proxy inherited")
	}
	for _, number := range []int{1, 2} {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if r.Method != "POST" || r.URL.Path != "/rpc" || r.Header.Get("Authorization") != "Bearer "+strings.Repeat("fixture", 6) {
				t.Error("invalid local request")
			}
			json.NewEncoder(w).Encode(map[string]any{"result": map[string]any{"number": number}})
		}))
		pairing(t, profile, server)
		value, err := backend.Call(context.Background(), "status", nil, time.Second)
		if err != nil || value["number"] != float64(number) {
			t.Fatalf("call failed: %v", err)
		}
		server.Close()
	}
}

func TestRedirectCannotReceivePairingKey(t *testing.T) {
	reached := false
	target := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { reached = true }))
	defer target.Close()
	source := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { http.Redirect(w, r, target.URL, 302) }))
	defer source.Close()
	profile := t.TempDir()
	pairing(t, profile, source)
	backend, _ := NewBackend(profile, "Fixture")
	_, err := backend.Call(context.Background(), "status", nil, time.Second)
	if err != ErrUnavailable || reached {
		t.Fatal("redirect was followed or unsafe error exposed")
	}
}

func TestErrorsContainNoPairingDetailsAndResponsesAreBounded(t *testing.T) {
	profile := t.TempDir()
	backend, _ := NewBackend(profile, "Fixture")
	_, err := backend.Call(context.Background(), "status", nil, time.Second)
	if err != ErrUnavailable || strings.Contains(err.Error(), profile) {
		t.Fatal("profile exposed")
	}
	for _, body := range []string{strings.Repeat("x", 262145), "not JSON", `{"error":"Unsupported MCP method"}`} {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { w.Write([]byte(body)) }))
		pairing(t, profile, server)
		_, err = backend.Call(context.Background(), "status", nil, time.Second)
		server.Close()
		if err == nil {
			t.Fatal("invalid response accepted")
		}
		if strings.HasPrefix(body, `{"error"`) && err.Error() != updateApp {
			t.Fatal("old app error not explained")
		}
	}
}
