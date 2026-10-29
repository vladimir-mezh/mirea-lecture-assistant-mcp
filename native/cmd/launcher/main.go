package main

import (
	"flag"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"

	"github.com/vladimir-mezh/mirea-lecture-assistant-mcp/native/internal/buildinfo"
	"github.com/vladimir-mezh/mirea-lecture-assistant-mcp/native/internal/installation"
)

func main() {
	profile := flag.String("profile", "", "Application profile")
	name := flag.String("client-name", "MCP-клиент", "Client display name")
	version := flag.Bool("version", false, "Print version")
	flag.Parse()
	if *version {
		fmt.Println(buildinfo.Version)
		return
	}
	if *profile == "" {
		fmt.Fprintln(os.Stderr, "--profile is required")
		os.Exit(2)
	}
	selected, err := installation.Select(filepath.Join(*profile, "mcp"))
	if err != nil {
		fmt.Fprintln(os.Stderr, installation.ErrInstall)
		os.Exit(1)
	}
	command := exec.Command(selected, "--profile", *profile, "--client-name", *name)
	command.Stdin, command.Stdout, command.Stderr = os.Stdin, os.Stdout, os.Stderr
	hideChildWindow(command)
	if err := command.Run(); err != nil {
		if exit, ok := err.(*exec.ExitError); ok {
			os.Exit(exit.ExitCode())
		}
		fmt.Fprintln(os.Stderr, "Cannot start the installed MCP adapter")
		os.Exit(1)
	}
}
