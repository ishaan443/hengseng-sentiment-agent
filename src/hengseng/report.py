"""Single-file, offline dashboard. All data is escaped before entering HTML."""
from __future__ import annotations

import json
from pathlib import Path


def write_report(path, payload):
    data = json.dumps(payload, ensure_ascii=False, allow_nan=False).replace("<", "\\u003c").replace("&", "\\u0026")
    template = Path(__file__).with_name("report_template.html").read_text(encoding="utf-8")
    Path(path).write_text(template.replace("__REPORT_DATA__", data), encoding="utf-8")
