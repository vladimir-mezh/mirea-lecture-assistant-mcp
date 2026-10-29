package main

import (
	"context"
	"flag"
	"fmt"
	"os"
	"os/signal"
	"path/filepath"

	"github.com/modelcontextprotocol/go-sdk/mcp"
	"github.com/vladimir-mezh/mirea-lecture-assistant-mcp/native/internal/adapter"
	"github.com/vladimir-mezh/mirea-lecture-assistant-mcp/native/internal/buildinfo"
)

func main() {
	profile := flag.String("profile", filepath.Join(os.Getenv("LOCALAPPDATA"), "MireaLectureAssistant"), "Application profile")
	name := flag.String("client-name", "MCP-клиент", "Client display name")
	version := flag.Bool("version", false, "Print version")
	flag.Parse()
	if *version {
		fmt.Println(buildinfo.Version)
		return
	}
	backend, err := adapter.NewBackend(*profile, *name)
	if err != nil {
		fmt.Fprintln(os.Stderr, "Cannot initialize MCP adapter")
		os.Exit(1)
	}
	server, err := adapter.NewServer(backend)
	if err != nil {
		fmt.Fprintln(os.Stderr, "Invalid MCP build")
		os.Exit(1)
	}
	ctx, cancel := signal.NotifyContext(context.Background(), os.Interrupt)
	defer cancel()
	backend.Start()
	defer backend.Stop()
	if server.Run(ctx, &mcp.StdioTransport{}) != nil && ctx.Err() == nil {
		fmt.Fprintln(os.Stderr, "MCP connection closed")
	}
}
