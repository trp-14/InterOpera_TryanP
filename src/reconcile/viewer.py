"""Generate a single, self-contained viewer.html from a completed run's
artifacts (BUILD_PLAN.md Step 13 — bonus, only after Steps 5-9).

Reads only `figures.json` (already written by `run`) and the provided
answer key for the delta column — never recomputes a figure. The output is
one HTML file with inline CSS and no JS at all: no server, no build step,
nothing for the page itself to compute.
"""
from __future__ import annotations

import html


def _delta_for(figure: dict, expected: dict | None) -> tuple[str, str]:
    """Returns (delta_text, css_class)."""
    if expected is None:
        return "no reference", "na"
    if figure.get("status") == "ERROR":
        return "n/a (figure errored)", "na"

    matches = figure.get("value") == expected.get("value") and figure.get("status") == expected.get("status")
    if matches:
        return "match", "match"
    return f"expected {expected.get('value')} ({expected.get('status')}), got {figure.get('value')} ({figure.get('status')})", "mismatch"


def _row_html(figure: dict, reference: dict[str, dict]) -> str:
    name = figure["figure"]
    delta_text, delta_class = _delta_for(figure, reference.get(name))

    if figure.get("status") == "ERROR":
        value, status, limit, utilization, path, rule = "ERROR", "ERROR", "n/a", "n/a", "", ""
        citation_html = html.escape(figure.get("error", ""))
    else:
        value = figure.get("value", "")
        status = figure.get("status", "")
        limit = figure.get("limit", "")
        utilization = figure.get("utilization", "")
        path = figure.get("graph_path", "")
        rule = figure.get("rule", "")
        citation = figure.get("citation")
        if citation:
            citation_html = (
                f"{html.escape(citation['source_doc'])} p.{citation['page']} "
                f"({html.escape(citation['chunk_id'])})<br>"
                f"<span class=\"muted\">{html.escape(citation['passage_summary'])}</span>"
            )
        else:
            citation_html = '<span class="muted">none</span>'

    status_class = status.lower().replace(" ", "-")

    return f"""
        <tr>
          <td>{html.escape(name)}</td>
          <td>{html.escape(value)}</td>
          <td class="status {status_class}">{html.escape(status)}</td>
          <td>{html.escape(limit)}</td>
          <td>{html.escape(utilization)}</td>
          <td class="delta {delta_class}">{html.escape(delta_text)}</td>
          <td class="path">{html.escape(path)}</td>
          <td>{citation_html}</td>
          <td class="muted">{html.escape(rule)}</td>
        </tr>"""


def build_viewer_html(figures_payload: dict, reference: dict[str, dict], *, run_id: str, firm_label: str) -> str:
    figures = figures_payload.get("figures", [])
    narrative = figures_payload.get("narrative", "")

    rows_html = "".join(_row_html(fig, reference) for fig in figures)
    narrative_html = (
        html.escape(narrative)
        if narrative
        else '<span class="muted">(none — no ANTHROPIC_API_KEY, or rejected by the firewall)</span>'
    )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Compliance Report Viewer — {html.escape(run_id)}</title>
<style>
  :root {{ color-scheme: light dark; }}
  body {{ font-family: -apple-system, "Segoe UI", Helvetica, Arial, sans-serif; margin: 2rem; background: #fafafa; color: #1a1a1a; }}
  h1 {{ font-size: 1.4rem; margin-bottom: 0.2rem; }}
  .meta {{ color: #666; margin-bottom: 1.5rem; font-size: 0.9rem; }}
  table {{ border-collapse: collapse; width: 100%; font-size: 0.85rem; background: white; }}
  th, td {{ border: 1px solid #ddd; padding: 6px 8px; text-align: left; vertical-align: top; }}
  th {{ background: #f0f0f0; position: sticky; top: 0; }}
  .status.ok {{ color: #0a7a0a; font-weight: 600; }}
  .status.breach {{ color: #c0392b; font-weight: 600; }}
  .status.at-limit {{ color: #b8860b; font-weight: 600; }}
  .status.error {{ color: #c0392b; font-weight: 600; background: #fdecea; }}
  .delta.match {{ color: #0a7a0a; }}
  .delta.mismatch {{ color: #c0392b; font-weight: 600; }}
  .delta.na {{ color: #888; }}
  .path {{ font-family: ui-monospace, Consolas, monospace; font-size: 0.78rem; max-width: 260px; }}
  .muted {{ color: #888; font-size: 0.8rem; }}
  .narrative {{ background: white; border: 1px solid #ddd; padding: 1rem; margin-bottom: 1.5rem; max-width: 60rem; }}
  @media (prefers-color-scheme: dark) {{
    body {{ background: #1a1a1a; color: #eee; }}
    table, .narrative {{ background: #262626; }}
    th {{ background: #333; }}
    th, td {{ border-color: #444; }}
  }}
</style>
</head>
<body>
  <h1>Compliance Report Viewer</h1>
  <div class="meta">
    Run: {html.escape(run_id)} &middot; Firm: {html.escape(firm_label)} &middot;
    Read-only — this page runs no computation, it only displays an already-written figures.json
  </div>

  <div class="narrative"><strong>Narrative:</strong><br>{narrative_html}</div>

  <table>
    <thead>
      <tr>
        <th>Figure</th><th>Value</th><th>Status</th><th>Limit</th><th>Utilization</th>
        <th>Delta vs answer key</th><th>Graph path</th><th>Citation</th><th>Config rule</th>
      </tr>
    </thead>
    <tbody>{rows_html}
    </tbody>
  </table>
</body>
</html>
"""
