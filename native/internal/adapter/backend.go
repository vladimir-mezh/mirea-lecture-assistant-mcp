package adapter

import (
	"bytes"
	"context"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"
	"unicode"

	"github.com/vladimir-mezh/mirea-lecture-assistant-mcp/native/internal/buildinfo"
)

var ErrUnavailable = errors.New("Lecture Assistant unavailable. Open the app, install MCP and enable local access in its MCP tab.")

const updateApp = "This needs a newer Lecture Assistant: ask the user to update the app (Настройки → Обновления)."

// Backend knows only the app's local pairing file and bounded HTTP API.
// It never reads the database, credential store, browser profile or email.
type Backend struct {
	profile  string
	client   map[string]string
	mu       sync.Mutex
	http     *http.Client
	cancel   context.CancelFunc
	finished chan struct{}
}

func NewBackend(profile, name string) (*Backend, error) {
	var identifier [16]byte
	if _, err := rand.Read(identifier[:]); err != nil {
		return nil, ErrUnavailable
	}
	name = strings.Map(func(r rune) rune {
		if unicode.IsControl(r) {
			return -1
		}
		return r
	}, name)
	if strings.TrimSpace(name) == "" {
		name = "MCP-клиент"
	}
	runes := []rune(name)
	if len(runes) > 80 {
		name = string(runes[:80])
	}
	transport := http.DefaultTransport.(*http.Transport).Clone()
	transport.Proxy = nil // Never send the local pairing key to an environment proxy.
	return &Backend{profile: profile, client: map[string]string{
		"id": hex.EncodeToString(identifier[:]), "name": name,
		"version": buildinfo.Version, "state": "waiting",
	}, http: &http.Client{Transport: transport, CheckRedirect: func(_ *http.Request, _ []*http.Request) error {
		return http.ErrUseLastResponse // Authorization never follows a redirect.
	}}}, nil
}

func readPairing(path string) ([]byte, error) {
	file, err := os.Open(path)
	if err != nil {
		return nil, ErrUnavailable
	}
	defer file.Close()
	info, err := file.Stat()
	if err != nil || !info.Mode().IsRegular() || info.Size() > 65536 {
		return nil, ErrUnavailable
	}
	data, err := io.ReadAll(io.LimitReader(file, 65537))
	if err != nil || len(data) > 65536 {
		return nil, ErrUnavailable
	}
	return data, nil
}

func (b *Backend) Call(ctx context.Context, method string, params map[string]any, timeout time.Duration) (map[string]any, error) {
	data, err := readPairing(filepath.Join(b.profile, "mcp-connection.json"))
	if err != nil {
		return nil, ErrUnavailable
	}
	var pairing struct {
		Protocol int    `json:"protocol"`
		Port     int    `json:"port"`
		Token    string `json:"token"`
	}
	if json.Unmarshal(data, &pairing) != nil || pairing.Protocol != 1 || pairing.Port < 1 || pairing.Port > 65535 || len(pairing.Token) < 32 || len(pairing.Token) > 4096 {
		return nil, ErrUnavailable
	}
	if params == nil {
		params = map[string]any{}
	}
	b.mu.Lock()
	if method != "heartbeat" && method != "disconnect" {
		b.client["state"] = "connected"
	}
	client := make(map[string]string, len(b.client))
	for k, v := range b.client {
		client[k] = v
	}
	b.mu.Unlock()
	payload, err := json.Marshal(map[string]any{"protocol": 1, "client": client, "method": method, "params": params})
	if err != nil || len(payload) > 16384 {
		return nil, errors.New("MCP request is too large or invalid")
	}
	ctx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()
	request, err := http.NewRequestWithContext(ctx, "POST", fmt.Sprintf("http://127.0.0.1:%d/rpc", pairing.Port), bytes.NewReader(payload))
	if err != nil {
		return nil, ErrUnavailable
	}
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("Authorization", "Bearer "+pairing.Token)
	response, err := b.http.Do(request)
	if err != nil {
		return nil, ErrUnavailable
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		return nil, ErrUnavailable
	}
	data, err = io.ReadAll(io.LimitReader(response.Body, 262145))
	if err != nil || len(data) > 262144 {
		return nil, ErrUnavailable
	}
	var result map[string]json.RawMessage
	if json.Unmarshal(data, &result) != nil || result == nil {
		return nil, ErrUnavailable
	}
	if raw, exists := result["error"]; exists {
		var message string
		if json.Unmarshal(raw, &message) != nil || len(message) > 2048 {
			return nil, ErrUnavailable
		}
		if message == "Unsupported MCP method" {
			message = updateApp
		}
		return nil, errors.New(message)
	}
	if raw, exists := result["result"]; exists {
		data = raw
	}
	var value map[string]any
	if json.Unmarshal(data, &value) != nil || value == nil {
		return nil, ErrUnavailable
	}
	return value, nil
}

func (b *Backend) Start() {
	ctx, cancel := context.WithCancel(context.Background())
	b.cancel, b.finished = cancel, make(chan struct{})
	go func() {
		defer close(b.finished)
		ticker := time.NewTicker(10 * time.Second)
		defer ticker.Stop()
		for {
			_, _ = b.Call(ctx, "heartbeat", nil, 3*time.Second)
			select {
			case <-ctx.Done():
				return
			case <-ticker.C:
			}
		}
	}()
}

func (b *Backend) Stop() {
	if b.cancel != nil {
		b.cancel()
		<-b.finished
	}
	_, _ = b.Call(context.Background(), "disconnect", nil, 2*time.Second)
	b.http.CloseIdleConnections()
}
