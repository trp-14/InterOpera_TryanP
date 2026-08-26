package main

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"regexp"

	"github.com/wailsapp/wails/v2/pkg/runtime"
)

// App is the Go-side of the desktop shell. It never computes a figure or
// touches sample_docs/ itself — every number still comes from
// `python -m src.main`, exactly as CLAUDE.md requires. This layer only
// launches that CLI and hands its already-written artifacts to the UI.
type App struct {
	ctx  context.Context
	root string
}

func NewApp() *App {
	return &App{}
}

func (a *App) startup(ctx context.Context) {
	a.ctx = ctx
	a.root = findProjectRoot()
}

// ProjectStatus is polled by the frontend on load to decide which actions to
// offer (e.g. hide "Run" until a graph has been ingested).
type ProjectStatus struct {
	Root           string `json:"root"`
	Found          bool   `json:"found"`
	HasFrozenGraph bool   `json:"hasFrozenGraph"`
}

func (a *App) GetProjectStatus() ProjectStatus {
	found := a.root != "" && isProjectRoot(a.root)
	hasGraph := false
	if found {
		_, err := os.Stat(filepath.Join(a.root, "artifacts", "graph.json"))
		hasGraph = err == nil
	}
	return ProjectStatus{Root: a.root, Found: found, HasFrozenGraph: hasGraph}
}

// ChooseProjectRoot opens a native folder picker so the user can point the
// app at the repo when auto-detection fails (e.g. the .exe was copied
// somewhere else). The choice is validated and persisted for next launch.
func (a *App) ChooseProjectRoot() (ProjectStatus, error) {
	selected, err := runtime.OpenDirectoryDialog(a.ctx, runtime.OpenDialogOptions{
		Title: "Select the compliance-pipeline repo root (the folder containing src/main.py)",
	})
	if err != nil {
		return a.GetProjectStatus(), err
	}
	if selected == "" {
		return a.GetProjectStatus(), nil // user cancelled
	}
	if !isProjectRoot(selected) {
		return a.GetProjectStatus(), errors.New("that folder has no src/main.py and config/firm_a.yaml — pick the repo root")
	}

	a.root = selected
	if err := saveProjectRoot(selected); err != nil {
		return a.GetProjectStatus(), err
	}
	return a.GetProjectStatus(), nil
}

func (a *App) requireRoot() (string, error) {
	if a.root == "" || !isProjectRoot(a.root) {
		return "", errors.New("project root not set — use \"Select project folder\" first")
	}
	return a.root, nil
}

// RunIngest builds the graph and freezes it, auto-approving the human review
// gate. (The full manual-review workflow stays a CLI-only feature — see
// README.md in this folder.)
func (a *App) RunIngest() (CommandResult, error) {
	root, err := a.requireRoot()
	if err != nil {
		return CommandResult{}, err
	}
	return runPython(root, "ingest", "--auto-approve"), nil
}

// PipelineResult bundles a `run` invocation with the bonus HTML viewer built
// from that same run's figures.json, so the frontend has something to render
// immediately without a second round trip.
type PipelineResult struct {
	RunID      string `json:"runId"`
	RunOutput  string `json:"runOutput"`
	ExitCode   int    `json:"exitCode"`
	ViewerHTML string `json:"viewerHtml"`
}

var runIDPattern = regexp.MustCompile(`Run ID:\s*(run_[a-f0-9]+)`)

func (a *App) RunPipeline(firm string) (PipelineResult, error) {
	root, err := a.requireRoot()
	if err != nil {
		return PipelineResult{}, err
	}

	runResult := runPython(root, "run", "--firm", firm)
	result := PipelineResult{RunOutput: runResult.Output, ExitCode: runResult.ExitCode}

	match := runIDPattern.FindStringSubmatch(runResult.Output)
	if match == nil {
		// Nothing to view — hand back the raw CLI output (e.g. "no frozen
		// graph" or a config error) so the user can see why.
		return result, nil
	}
	result.RunID = match[1]

	viewerResult := runPython(root, "viewer", "--run-id", result.RunID)
	if viewerResult.ExitCode != 0 {
		result.RunOutput += "\n\n[viewer]\n" + viewerResult.Output
		return result, nil
	}

	viewerPath := filepath.Join(root, "artifacts", result.RunID, "viewer.html")
	html, err := os.ReadFile(viewerPath)
	if err != nil {
		result.RunOutput += "\n\n[viewer] wrote no viewer.html: " + err.Error()
		return result, nil
	}
	result.ViewerHTML = string(html)
	return result, nil
}

func (a *App) RunEvaluate(firm string) (CommandResult, error) {
	root, err := a.requireRoot()
	if err != nil {
		return CommandResult{}, err
	}
	return runPython(root, "evaluate", "--firm", firm), nil
}

func (a *App) TraceFigure(figureName string, firm string) (CommandResult, error) {
	root, err := a.requireRoot()
	if err != nil {
		return CommandResult{}, err
	}
	return runPython(root, "trace", figureName, "--firm", firm), nil
}

func (a *App) VerifyDeterminism(firm string) (CommandResult, error) {
	root, err := a.requireRoot()
	if err != nil {
		return CommandResult{}, err
	}
	return runPython(root, "verify-determinism", "--firm", firm), nil
}
