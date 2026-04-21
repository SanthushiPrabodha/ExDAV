"""
HTML report renderer for Ex-DAV showcase outputs.
"""

from __future__ import annotations

from html import escape
from typing import Any, Dict


def render_html_report(result: Dict[str, Any]) -> str:
    """Render a simple, demo-friendly HTML report from pipeline JSON output."""
    verdict = escape(str(result.get("final_verdict", "N/A")))
    confidence = escape(str(result.get("confidence_level", "N/A")))
    explanation = result.get("explanation", []) or []
    metadata = result.get("extracted_metadata", {}) or {}
    issues = result.get("validation_issues", []) or []
    flags = result.get("semantic_flags", []) or []

    explanation_html = "".join(f"<li>{escape(str(item))}</li>" for item in explanation)
    metadata_html = "".join(
        f"<tr><td>{escape(str(k))}</td><td>{escape(str(v))}</td></tr>"
        for k, v in metadata.items()
    )
    issues_html = "".join(
        "<li>"
        + escape(
            f"{issue.get('code', 'UNKNOWN')} ({issue.get('field', '-')}) - "
            f"{issue.get('message', '')}"
        )
        + "</li>"
        for issue in issues
    )
    flags_html = "".join(f"<li>{escape(str(flag))}</li>" for flag in flags)

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Ex-DAV Report</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 2rem; line-height: 1.45; }}
    .card {{ border: 1px solid #ddd; border-radius: 8px; padding: 1rem; margin-bottom: 1rem; }}
    h1, h2 {{ margin-top: 0; }}
    table {{ border-collapse: collapse; width: 100%; }}
    td, th {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
    .badge {{ display: inline-block; padding: 4px 10px; border-radius: 999px; background: #f3f4f6; }}
  </style>
</head>
<body>
  <h1>Ex-DAV Showcase Report</h1>
  <div class="card">
    <h2>Final Decision</h2>
    <p><strong>Verdict:</strong> <span class="badge">{verdict}</span></p>
    <p><strong>Confidence:</strong> <span class="badge">{confidence}</span></p>
  </div>

  <div class="card">
    <h2>Explanation</h2>
    <ul>{explanation_html or "<li>None</li>"}</ul>
  </div>

  <div class="card">
    <h2>Extracted Metadata</h2>
    <table>
      <thead><tr><th>Field</th><th>Value</th></tr></thead>
      <tbody>{metadata_html or "<tr><td colspan='2'>None</td></tr>"}</tbody>
    </table>
  </div>

  <div class="card">
    <h2>Validation Issues</h2>
    <ul>{issues_html or "<li>None</li>"}</ul>
  </div>

  <div class="card">
    <h2>Semantic Flags</h2>
    <ul>{flags_html or "<li>None</li>"}</ul>
  </div>
</body>
</html>
"""

