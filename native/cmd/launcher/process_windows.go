package main

import (
	"os/exec"
	"syscall"
)

func hideChildWindow(command *exec.Cmd) {
	command.SysProcAttr = &syscall.SysProcAttr{CreationFlags: 0x08000000} // CREATE_NO_WINDOW
}
