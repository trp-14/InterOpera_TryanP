"use client";

import { useEffect, useState } from "react";
import {
  GetProjectStatus,
  ChooseProjectRoot,
  GetInputFiles,
  RunIngest,
  RunPipeline,
  RunEvaluate,
  TraceFigure,
  VerifyDeterminism,
} from "@/wailsjs/go/main/App";
import type { main } from "@/wailsjs/go/models";

type Firm = "A" | "B";

export default function Home() {
  const [status, setStatus] = useState<main.ProjectStatus | null>(null);
  const [firm, setFirm] = useState<Firm>("A");
  const [busy, setBusy] = useState<string | null>(null);
  const [log, setLog] = useState<string>("");
  const [viewerHtml, setViewerHtml] = useState<string>("");
  const [figureName, setFigureName] = useState("portfolio_modified_duration");
  const [inputFiles, setInputFiles] = useState<main.InputFile[]>([]);

  const refreshStatus = () => {
    GetProjectStatus().then(setStatus);
  };

  useEffect(() => {
    refreshStatus();
  }, []);

  useEffect(() => {
    if (status?.found) {
      GetInputFiles(firm).then(setInputFiles).catch(() => setInputFiles([]));
    }
  }, [status?.found, firm]);

  const runAction = async (label: string, action: () => Promise<{ output?: string; runOutput?: string; viewerHtml?: string }>) => {
    setBusy(label);
    setLog(`> ${label}\n`);
    try {
      const result = await action();
      setLog((prev) => prev + (result.output ?? result.runOutput ?? ""));
      if (result.viewerHtml) setViewerHtml(result.viewerHtml);
    } catch (err) {
      setLog((prev) => prev + "\nERROR: " + String(err));
    } finally {
      setBusy(null);
      refreshStatus();
    }
  };

  if (!status) {
    return <main style={styles.page}>Loading…</main>;
  }

  if (!status.found) {
    return (
      <main style={styles.page}>
        <h1 style={styles.h1}>Meridian Compliance Desktop</h1>
        <p style={styles.muted}>
          Could not find the compliance-pipeline repo (a folder containing{" "}
          <code>src/main.py</code> and <code>config/firm_a.yaml</code>).
        </p>
        <button
          style={styles.buttonPrimary}
          onClick={() => ChooseProjectRoot().then(setStatus)}
        >
          Select project folder…
        </button>
      </main>
    );
  }

  return (
    <main style={styles.page}>
      <header style={styles.header}>
        <h1 style={styles.h1}>Meridian Compliance Desktop</h1>
        <span style={styles.muted}>{status.root}</span>
      </header>

      <section style={styles.inputFiles}>
        <h2 style={styles.h2}>Input files (fixed for this run — no file picker by design)</h2>
        <ul style={styles.inputFileList}>
          {inputFiles.map((f) => (
            <li key={f.path} style={styles.inputFileRow}>
              <span style={f.found ? styles.badgeOk : styles.badgeMissing}>{f.found ? "✓" : "✗"}</span>
              <span>{f.label}</span>
              <code style={styles.inputFilePath}>{f.path}</code>
              {f.found && <span style={styles.muted}>{(f.bytes / 1024).toFixed(1)} KB</span>}
            </li>
          ))}
        </ul>
      </section>

      <section style={styles.controls}>
        <div style={styles.firmToggle}>
          {(["A", "B"] as Firm[]).map((f) => (
            <button
              key={f}
              onClick={() => setFirm(f)}
              style={f === firm ? styles.firmButtonActive : styles.firmButton}
            >
              Firm {f}
            </button>
          ))}
        </div>

        <button
          style={styles.button}
          disabled={busy !== null}
          onClick={() => runAction("ingest --auto-approve", () => RunIngest())}
        >
          1. Ingest (auto-approve)
        </button>

        <button
          style={styles.buttonPrimary}
          disabled={busy !== null || !status.hasFrozenGraph}
          onClick={() => runAction(`run --firm ${firm}`, () => RunPipeline(firm))}
        >
          2. Run pipeline
        </button>

        <button
          style={styles.button}
          disabled={busy !== null || !status.hasFrozenGraph}
          onClick={() => runAction(`evaluate --firm ${firm}`, () => RunEvaluate(firm))}
        >
          3. Evaluate
        </button>

        <button
          style={styles.button}
          disabled={busy !== null || !status.hasFrozenGraph}
          onClick={() => runAction(`verify-determinism --firm ${firm}`, () => VerifyDeterminism(firm))}
        >
          Verify determinism
        </button>

        <div style={styles.traceRow}>
          <input
            style={styles.input}
            value={figureName}
            onChange={(e) => setFigureName(e.target.value)}
            placeholder="figure name"
          />
          <button
            style={styles.button}
            disabled={busy !== null || !status.hasFrozenGraph}
            onClick={() => runAction(`trace ${figureName} --firm ${firm}`, () => TraceFigure(figureName, firm))}
          >
            Trace
          </button>
        </div>

        {!status.hasFrozenGraph && (
          <p style={styles.muted}>Run step 1 (ingest) before running the pipeline.</p>
        )}
      </section>

      <section style={styles.outputGrid}>
        <div style={styles.panel}>
          <h2 style={styles.h2}>CLI output</h2>
          <pre style={styles.pre}>{log || "(nothing run yet)"}</pre>
        </div>
        <div style={styles.panel}>
          <h2 style={styles.h2}>Report viewer</h2>
          {viewerHtml ? (
            <iframe title="report viewer" srcDoc={viewerHtml} style={styles.iframe} />
          ) : (
            <p style={styles.muted}>Run the pipeline to see the figures viewer here.</p>
          )}
        </div>
      </section>
    </main>
  );
}

const styles: Record<string, React.CSSProperties> = {
  page: { padding: "1.5rem 2rem", display: "flex", flexDirection: "column", gap: "1rem", height: "100vh" },
  header: { display: "flex", alignItems: "baseline", gap: "1rem" },
  h1: { fontSize: "1.3rem", margin: 0 },
  h2: { fontSize: "1rem", margin: "0 0 0.5rem" },
  muted: { color: "#777", fontSize: "0.85rem" },
  inputFiles: { border: "1px solid #e0e0e0", borderRadius: 8, padding: "0.7rem 0.9rem" },
  inputFileList: { listStyle: "none", display: "flex", flexDirection: "column", gap: "0.3rem", fontSize: "0.85rem" },
  inputFileRow: { display: "flex", alignItems: "center", gap: "0.6rem" },
  inputFilePath: { color: "#555", background: "#f4f4f4", padding: "0.1rem 0.4rem", borderRadius: 4, fontSize: "0.78rem" },
  badgeOk: { color: "#0a7a0a", fontWeight: 700 },
  badgeMissing: { color: "#c0392b", fontWeight: 700 },
  controls: { display: "flex", flexWrap: "wrap", alignItems: "center", gap: "0.6rem" },
  firmToggle: { display: "flex", border: "1px solid #ccc", borderRadius: 6, overflow: "hidden" },
  firmButton: { padding: "0.4rem 0.9rem", border: "none", background: "white", cursor: "pointer" },
  firmButtonActive: { padding: "0.4rem 0.9rem", border: "none", background: "#1b2636", color: "white", cursor: "pointer" },
  button: { padding: "0.5rem 0.9rem", borderRadius: 6, border: "1px solid #ccc", background: "white", cursor: "pointer" },
  buttonPrimary: { padding: "0.5rem 0.9rem", borderRadius: 6, border: "none", background: "#1b2636", color: "white", cursor: "pointer" },
  traceRow: { display: "flex", gap: "0.4rem" },
  input: { padding: "0.45rem 0.6rem", borderRadius: 6, border: "1px solid #ccc", minWidth: 220 },
  outputGrid: { display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem", flex: 1, minHeight: 0 },
  panel: { display: "flex", flexDirection: "column", minHeight: 0, border: "1px solid #e0e0e0", borderRadius: 8, padding: "0.8rem" },
  pre: { flex: 1, overflow: "auto", whiteSpace: "pre-wrap", fontSize: "0.8rem", margin: 0 },
  iframe: { flex: 1, border: "1px solid #e0e0e0", borderRadius: 6 },
};
