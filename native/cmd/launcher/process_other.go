//go:build !windows

package main

import "os/exec"

func hideChildWindow(_ *exec.Cmd) {}
