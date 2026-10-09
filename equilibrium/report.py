"""Portable offline HTML report, with no external assets or script execution."""
from html import escape
from pathlib import Path

from .codec import canonical


def write_report(bundle: dict, path: str | Path) -> None:
    rows = []
    for step in bundle["steps"]:
        result = step["result"]
        action = result.get("action", {})
        rows.append("<tr>" + "".join(f"<td>{escape(str(value))}</td>" for value in (
            step["event"], step["at_ms"], action.get("state", result.get("state", "")),
            result.get("authorized", False), result["reason"], canonical(action.get("outputs", {})),
            step["adapter_calls"])) + "</tr>")
    final = bundle["final"]
    html = """<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'">
<title>IX-Equilibrium simulation evidence</title><style>
body{background:#0c110e;color:#dce8df;font:15px system-ui;margin:0;padding:32px}
main{max-width:1400px;margin:auto}h1{font-size:30px;color:#73e09b}p{line-height:1.65}
.card{background:#17221b;border:1px solid #2b4534;border-radius:12px;padding:20px;margin:20px 0}
table{border-collapse:collapse;width:100%;font-size:13px}th,td{padding:12px;text-align:left;border-bottom:1px solid #314438}
td:nth-child(6){font-family:monospace;overflow-wrap:anywhere}th{color:#73e09b}code{overflow-wrap:anywhere}
.scroll{overflow:auto}details{margin-top:24px}pre{white-space:pre-wrap;overflow-wrap:anywhere;color:#b9d9c3}
</style><main><h1>IX-Equilibrium</h1><p>Deterministic simulation evidence. Authority and reviews in this report are synthetic fixtures.</p>"""
    html += f'<div class="card"><b>{escape(bundle["scenario"]["name"])}</b><p>Final state: {escape(final["state"])} · Adapter calls: {final["adapter_calls"]} · Stop requests: {final["stop_requests"]}</p><code>Source SHA-256: {bundle["source_sha256"]}</code></div>'
    html += '<div class="card scroll"><table><thead><tr><th>Event</th><th>Time (ms)</th><th>State</th><th>Authorized</th><th>Reason</th><th>Setpoints (SI)</th><th>Calls</th></tr></thead><tbody>'
    html += "".join(rows) + "</tbody></table></div>"
    html += f'<details><summary>Complete evidence</summary><pre>{escape(canonical(bundle))}</pre></details></main></html>'
    Path(path).write_text(html, encoding="utf-8")

