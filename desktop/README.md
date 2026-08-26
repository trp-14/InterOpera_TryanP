# Meridian Compliance Desktop

A desktop shell around the compliance-pipeline CLI in `../src`. This exists
purely to demonstrate a Go + React/Next.js layer on top of the pipeline — it
is **not** part of the graded assignment and does not change how any figure
is computed.

## What it is, and isn't

- The engine (`src/compute`, `src/graph`, `src/ingestion`) is untouched. This
  app never computes a figure itself — every button here just shells out to
  `python -m src.main <command>` and displays what that process writes.
- It packages into a single native `.exe` (via [Wails](https://wails.io)),
  with a React/Next.js frontend (static-exported, embedded in the binary)
  talking to a Go backend over Wails' generated bindings.
- The human-in-the-loop graph review step (`approve-graph` when a node needs
  manual review) is not wired into the UI — this app always ingests with
  `--auto-approve`, matching the CLI's own demo-run switch. Use the CLI
  directly for the full manual review workflow.

## Layout

```
desktop/
  main.go, app.go, pyrunner.go, config.go   — Go backend (Wails app)
  frontend/                                 — Next.js app (output: "export")
  frontend/wailsjs/                         — generated bindings, do not edit
  wails.json                                — Wails project config
```

## Requirements

- Go 1.25+, Node 18+, the [Wails v2 CLI](https://wails.io/docs/gettingstarted/installation)
- A working Python environment for the pipeline itself, ideally the repo's
  own `.venv` (see the root `README.md` / `requirements.txt`) — the app
  prefers `<repo root>/.venv/Scripts/python.exe` and falls back to whatever
  `python` is on `PATH`.

## Running it

```bash
cd desktop
wails dev      # hot-reloading dev window (runs `npm run dev` for you)
```

On first launch the app looks for the repo root (a folder with `src/main.py`
and `config/firm_a.yaml`) by walking up from the working directory and from
the executable's own location. If it can't find it, use "Select project
folder…" in the app — the choice is remembered for next time.

## Building the .exe

```bash
cd desktop
wails build
```

Output: `desktop/build/bin/meridian-desktop.exe`. This is a single
self-contained binary (the frontend is embedded); it still needs Python and
this repo's dependencies available on the machine it runs on, since it is a
shell around the CLI, not a reimplementation of it.
