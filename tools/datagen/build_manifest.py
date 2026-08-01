"""產生 manifest.json：seed、D 日、每個檔案的筆數與 sha256。

同一 seed 重跑必須得到完全相同的 sha256，否則代表生成器有非確定性來源。
"""

from __future__ import annotations

import hashlib
import json

from common import D_DAY, OUT_DIR, SEED, iso, report, write_json

MANIFEST_NAME = "manifest.json"


def _count_rows(path) -> int | None:
    if path.suffix == ".jsonl":
        return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line)
    if path.suffix == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        return len(payload) if isinstance(payload, list) else None
    return None


def build() -> None:
    files = []
    for path in sorted(OUT_DIR.rglob("*")):
        if not path.is_file() or path.name == MANIFEST_NAME:
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        files.append(
            {
                "path": str(path.relative_to(OUT_DIR)),
                "bytes": path.stat().st_size,
                "rows": _count_rows(path),
                "sha256": digest,
            }
        )

    manifest = {
        "dataset_version": "1.1.0",
        "seed": SEED,
        "d_day": iso(D_DAY),
        "generated_by": "tools/datagen/run_all.py",
        "determinism": "同一 seed 重跑，所有 sha256 必須完全相同",
        "file_count": len(files),
        "total_rows": sum(f["rows"] or 0 for f in files),
        "files": files,
    }
    report(write_json(MANIFEST_NAME, manifest), len(files))


if __name__ == "__main__":
    build()
