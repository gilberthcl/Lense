"""
Parse a final Threat Hunt report (.docx) into its structural sections so a
Training Hunt can be pre-filled from it: the findings (one per finding heading),
the methodology / action-plan section, and the MITRE ATT&CK coverage table.

Deterministic, heading-driven — NO LLM. Robust to report-to-report variation:
  • The Findings section is ANY heading whose text contains "finding" (e.g.
    "Findings", "Detailed Findings", "Key Findings"), at the shallowest such level.
  • Inside it, each finding is a heading at the shallowest sub-level present
    (Heading 2 OR 3 — whichever the report uses); its body runs to the next.
  • Fallback: if findings aren't styled as headings, split on fully-bold lines.
  • The MITRE coverage is a table whose header names tactics/techniques.

Extracted findings are RAW text (title + body) — NOT structured/grounded here.
"""
from __future__ import annotations

import io

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph

from app.services.doc_loader import _iter_blocks, _table_to_text


def _heading_level(p: Paragraph) -> int | None:
    name = (p.style.name or "") if p.style else ""
    if name == "Title":
        return 0
    if name.startswith("Heading "):
        try:
            return int(name.split()[-1])
        except ValueError:
            return None
    return None


def _is_all_bold(p: Paragraph) -> bool:
    """A short paragraph whose every non-blank run is bold — a finding title that
    wasn't given a heading style."""
    runs = [r for r in p.runs if r.text.strip()]
    if not runs or len(p.text.strip()) > 160:
        return False
    return all(r.bold for r in runs)


def _looks_like_mitre_header(first_row: str) -> bool:
    h = first_row.lower()
    return ("mitre" in h or "att&ck" in h or "attack" in h
            or ("tactic" in h and "technique" in h))


def parse_report_docx(data: bytes) -> dict:
    """Return {sections, section_names, findings, methodology_text, mitre_table}.
    `findings` = [{"title","body"}] (raw, one per finding)."""
    document = Document(io.BytesIO(data))

    # Pass 1: collect blocks in order with heading level + bold flag.
    # blk = {"kind": "p"|"table", "text", "level": int|None, "bold": bool}
    blocks: list[dict] = []
    for b in _iter_blocks(document):
        if isinstance(b, Paragraph):
            blocks.append({"kind": "p", "text": b.text.strip(),
                           "level": _heading_level(b), "bold": _is_all_bold(b)})
        elif isinstance(b, Table):
            blocks.append({"kind": "table", "text": _table_to_text(b),
                           "level": None, "bold": False})

    # Sections keyed by their top-level heading (level <= 1).
    sections: dict[str, list[str]] = {}
    cur_h1: str | None = None
    mitre_table: str | None = None
    findings_idx: int | None = None
    findings_level: int | None = None

    for i, blk in enumerate(blocks):
        if blk["kind"] == "p":
            lvl, text = blk["level"], blk["text"]
            if lvl is not None and lvl <= 1 and text:
                cur_h1 = text
                sections.setdefault(cur_h1, [])
                # Remember the Findings section (shallowest "finding*" heading).
                if "finding" in text.lower() and findings_idx is None:
                    findings_idx, findings_level = i, lvl
                continue
            if not text and blk["kind"] == "p":
                continue
            if cur_h1:
                sections[cur_h1].append(text)
        else:  # table
            ttext = blk["text"]
            if not ttext.strip():
                continue
            if mitre_table is None and _looks_like_mitre_header(ttext.split("\n", 1)[0]):
                mitre_table = ttext
            if cur_h1:
                sections[cur_h1].append(f"[TABLE]\n{ttext}\n[/TABLE]")

    findings = _extract_findings(blocks, findings_idx, findings_level)

    sections_text = {k: "\n".join(v).strip() for k, v in sections.items()}
    methodology_text = ""
    for name, txt in sections_text.items():
        if "methodolog" in name.lower() or "action plan" in name.lower():
            methodology_text = f"{name}\n{txt}".strip()
            break

    return {
        "sections": sections_text,
        "section_names": list(sections_text.keys()),
        "findings": findings,
        "methodology_text": methodology_text,
        "mitre_table": mitre_table,
    }


def _extract_findings(blocks: list[dict], start: int | None, sec_level: int | None) -> list[dict]:
    """Findings live between the Findings heading (`start`) and the next heading at
    level <= sec_level. Each is delimited by the shallowest sub-heading level in
    that range; if there are none, fall back to fully-bold lines."""
    if start is None or sec_level is None:
        return []

    # Span = [start+1, end).
    end = len(blocks)
    for j in range(start + 1, len(blocks)):
        lvl = blocks[j]["level"]
        if lvl is not None and lvl <= sec_level:
            end = j
            break
    span = blocks[start + 1:end]
    if not span:
        return []

    # Delimiter level = the shallowest heading deeper than the section.
    sub_levels = [b["level"] for b in span if b["level"] is not None and b["level"] > sec_level]
    use_bold = not sub_levels
    delim_level = min(sub_levels) if sub_levels else None

    def is_title(b: dict) -> bool:
        if b["kind"] != "p" or not b["text"]:
            return False
        if use_bold:
            return b["bold"]
        return b["level"] == delim_level

    findings: list[dict] = []
    cur: dict | None = None
    for b in span:
        if is_title(b):
            if cur:
                findings.append({"title": cur["title"], "body": "\n".join(cur["parts"]).strip()})
            cur = {"title": b["text"], "parts": []}
        elif cur is not None and b["text"]:
            chunk = b["text"] if b["kind"] == "p" else f"[TABLE]\n{b['text']}\n[/TABLE]"
            cur["parts"].append(chunk)
    if cur:
        findings.append({"title": cur["title"], "body": "\n".join(cur["parts"]).strip()})
    return [f for f in findings if f["title"]]
