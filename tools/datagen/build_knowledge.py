"""複製知識來源，並產生可直接同步至 Bedrock KB 的小文件與 metadata。

內容是人寫的（不是生成的），來源在 tools/datagen/knowledge/，
`data/mock/knowledge/` 保留原始合併文件；`data/mock/knowledge_base/`
則按二級標題切分，每個 Markdown 都有 Bedrock sidecar metadata。
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from common import OUT_DIR, report

SOURCE_DIR = Path(__file__).resolve().parent / "knowledge"
README_SOURCE = Path(__file__).resolve().parent / "dataset_readme.md"

SECTION_PATTERN = re.compile(r"^##\s+(?P<title>.+?)\s*$", re.MULTILINE)


def _parse_frontmatter(text: str) -> tuple[dict[str, object], str]:
    if not text.startswith("---\n"):
        raise ValueError("knowledge source 缺少 YAML frontmatter")
    _, frontmatter, body = text.split("---\n", 2)
    metadata: dict[str, object] = {}
    for line in frontmatter.splitlines():
        if not line.strip() or ":" not in line:
            continue
        key, raw_value = line.split(":", 1)
        value = raw_value.strip()
        if value.startswith("[") and value.endswith("]"):
            metadata[key.strip()] = [
                item.strip() for item in value[1:-1].split(",") if item.strip()
            ]
        else:
            metadata[key.strip()] = value
    return metadata, body.strip()


def _section_kind(title: str) -> str:
    if "高風險" in title or "安全" in title:
        return "safety"
    if "常見" in title or "問答" in title:
        return "faq"
    if "條款" in title or "政策" in title:
        return "terms"
    if "SOP" in title.upper() or "流程" in title:
        return "sop"
    return "notice"


def _split_sections(body: str) -> tuple[str, list[tuple[str, str]]]:
    matches = list(SECTION_PATTERN.finditer(body))
    if not matches:
        raise ValueError("knowledge source 沒有二級標題，無法切分")
    document_title = body[: matches[0].start()].strip()
    sections: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        sections.append((match.group("title"), body[match.end() : end].strip()))
    return document_title, sections


def _build_upload_documents(source: Path, target_root: Path) -> int:
    source_metadata, body = _parse_frontmatter(source.read_text(encoding="utf-8"))
    document_title, sections = _split_sections(body)
    service_type = str(source_metadata["service_type"])
    service_dir = target_root / service_type
    service_dir.mkdir(parents=True, exist_ok=True)
    boundary_fields = source_metadata.get("never_authoritative_for", [])
    boundary = ", ".join(str(item) for item in boundary_fields)

    for index, (section_title, section_body) in enumerate(sections, start=1):
        doc_kind = _section_kind(section_title)
        filename = f"{index:02d}-{doc_kind}.md"
        target = service_dir / filename
        content = (
            f"{document_title}\n\n"
            f"## {section_title}\n\n"
            f"> 資料邊界：本文件只適用於靜態 {doc_kind} 知識；"
            f"{boundary} 必須改查即時工具。\n\n"
            f"{section_body}\n"
        )
        target.write_text(content, encoding="utf-8")

        sidecar = target.with_name(f"{target.name}.metadata.json")
        sidecar_payload = {
            "metadataAttributes": {
                "service_type": service_type,
                "doc_kind": doc_kind,
                "version": str(source_metadata["version"]),
                "effective_from": str(source_metadata["effective_from"]),
                "source": str(source_metadata["source"]),
                "source_doc_id": str(source_metadata["doc_id"]),
                "section_index": index,
                "authoritative_scope": "static_only",
            }
        }
        sidecar.write_text(
            json.dumps(sidecar_payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        report(target, content.count("\n"))
        report(sidecar, 1)
    return len(sections)


def build() -> None:
    target_dir = OUT_DIR / "knowledge"
    target_dir.mkdir(parents=True, exist_ok=True)
    upload_dir = OUT_DIR / "knowledge_base"
    if upload_dir.exists():
        shutil.rmtree(upload_dir)
    upload_dir.mkdir(parents=True)

    for source in sorted(SOURCE_DIR.glob("*.md")):
        target = target_dir / source.name
        target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
        report(target, source.read_text(encoding="utf-8").count("\n"))
        _build_upload_documents(source, upload_dir)

    readme = OUT_DIR / "README.md"
    readme.write_text(README_SOURCE.read_text(encoding="utf-8"), encoding="utf-8")
    report(readme, README_SOURCE.read_text(encoding="utf-8").count("\n"))


if __name__ == "__main__":
    build()
