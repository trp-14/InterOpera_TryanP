package main

import (
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
)

// isProjectRoot reports whether dir looks like the compliance-pipeline repo
// root (the same markers CLAUDE.md describes: the CLI entrypoint and the
// per-firm config files).
func isProjectRoot(dir string) bool {
	_, errMain := os.Stat(filepath.Join(dir, "src", "main.py"))
	_, errCfg := os.Stat(filepath.Join(dir, "config", "firm_a.yaml"))
	return errMain == nil && errCfg == nil
}

// findProjectRoot looks for the repo root without asking the user: first the
// path saved from a previous launch, then a walk upward from the working
// directory and from the executable's own location (covers both `wails dev`,
// where cwd is desktop/, and a built .exe sitting under desktop/build/bin/).
func findProjectRoot() string {
	if saved := loadSavedProjectRoot(); saved != "" && isProjectRoot(saved) {
		return saved
	}

	var starts []string
	if wd, err := os.Getwd(); err == nil {
		starts = append(starts, wd)
	}
	if exe, err := os.Executable(); err == nil {
		starts = append(starts, filepath.Dir(exe))
	}

	for _, start := range starts {
		dir := start
		for i := 0; i < 8; i++ {
			if isProjectRoot(dir) {
				return dir
			}
			parent := filepath.Dir(dir)
			if parent == dir {
				break
			}
			dir = parent
		}
	}
	return ""
}

// resolvePythonExe prefers the project's own virtualenv interpreter (so the
// desktop app uses exactly the pinned dependencies from requirements.txt)
// and falls back to whatever "python" is on PATH.
func resolvePythonExe(root string) string {
	candidate := filepath.Join(root, ".venv", "Scripts", "python.exe")
	if runtime.GOOS != "windows" {
		candidate = filepath.Join(root, ".venv", "bin", "python")
	}
	if _, err := os.Stat(candidate); err == nil {
		return candidate
	}
	return "python"
}

// CommandResult is what every CLI invocation returns to the frontend.
type CommandResult struct {
	Command  string `json:"command"`
	Output   string `json:"output"`
	ExitCode int    `json:"exitCode"`
}

func runPython(root string, args ...string) CommandResult {
	pythonExe := resolvePythonExe(root)
	fullArgs := append([]string{"-m", "src.main"}, args...)

	cmd := exec.Command(pythonExe, fullArgs...)
	cmd.Dir = root

	output, err := cmd.CombinedOutput()

	exitCode := 0
	if err != nil {
		if exitErr, ok := err.(*exec.ExitError); ok {
			exitCode = exitErr.ExitCode()
		} else {
			// The interpreter itself could not be started (e.g. no Python on
			// PATH) — surface that as output instead of losing it.
			output = append(output, []byte("\n"+err.Error())...)
			exitCode = -1
		}
	}

	return CommandResult{
		Command:  pythonExe + " -m src.main " + joinArgs(args),
		Output:   string(output),
		ExitCode: exitCode,
	}
}

func joinArgs(args []string) string {
	out := ""
	for i, a := range args {
		if i > 0 {
			out += " "
		}
		out += a
	}
	return out
}
