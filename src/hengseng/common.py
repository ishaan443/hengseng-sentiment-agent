from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path

import pandas as pd


@lru_cache(maxsize=100000)
def utc(value) -> pd.Timestamp:
    stamp = pd.Timestamp(value)
    if pd.isna(stamp) or stamp.tzinfo is None:
        raise ValueError(f"Timestamp needs an explicit timezone: {value!r}")
    return stamp.tz_convert("UTC")


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     default=str).encode()).hexdigest()


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str,
                               allow_nan=False), encoding="utf-8")
    temp.replace(path)


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def read_jsonl(path):
    path = Path(path)
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()] if path.exists() else []


def write_jsonl(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text("".join(json.dumps(r, ensure_ascii=False, default=str,
                                    allow_nan=False) + "\n" for r in rows), encoding="utf-8")
    temp.replace(path)
