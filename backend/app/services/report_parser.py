"""
Parse a final Threat Hunt report (.docx) into its structural sections so a
Training Hunt can be pre-filled from it: the findings (one per finding heading),
the methodology / action-plan section, and the MITRE ATT&CK coverage table.

Deterministic, heading-driven — NO LLM here. Reports follow a stable layout:
  • `Heading 1` delimits the major sections (Executive Summary, Background,
    Findings, Methodology, …).
  • Inside the Findings section, each finding is its own deeper heading
    (`Heading 2`/`Heading 3`); its body is everything until the next finding.
  • The MITRE coverage is a table whose header names tactics/techniques.

The extracted findings are RAW text (title + body). They are NOT structured or
grounded here — that happens later, once datasets are uploaded (per the workflow:
load the findings, but don't analyse until the data is present).
"""
from __future__ import annotations

import io

from docx import Document
from docx.text.paragraph import Paragraph

from app.services.doc_loader import _iter_blocks, _table_to_text


def _heading_level(p: Paragraph) -> int | None:
    """Heading depth for a paragraph (1 for 'Heading 1', …); None if not a heading.
    'Title' is treated as level 0."""
    name = (p.style.name or "") if p.style else ""
    if name == "Title":
        return 0
    if name.startswith("Heading "):
        try:
            return int(name.split()[-1])
        except ValueError:
            return None
    return None


def _is_findings_section(name: str | None) -> bool:
    return bool(name) and name.strip().lower().startswith("finding")


def _looks_like_mitre_header(first_row: str) -> bool:
    h = first_row.lower()
    return ("mitre" in h or "att&ck" in h or "attack" in h
            or ("tactic" in h and "technique" in h))


def parse_report_docx(data: bytes) -> dict:
    """Return {sections, findings, methodology_text, mitre_table, section_names}.

    `findings` = [{"title", "body"}] (raw text, one per finding heading)."""
    document = Document(io.BytesIO(data))

    sections: dict[str, list[str]] = {}
    findings: list[dict] = []
    cur_h1: str | None = None
    cur_finding: dict | None = None
    mitre_table: str | None = None

    def flush_finding() -> None:
        nonlocal cur_finding
        if cur_finding is not None:
            findings.append({
                "title": cur_finding["title"],
                "body": "\n".join(cur_finding["parts"]).strip(),
            })
            cur_finding = None

    for block in _iter_blocks(document):
        if isinstance(block, Paragraph):
            text = block.text.strip()
            lvl = _heading_level(block)
            if lvl is not None and lvl <= 1:
                # A new major section (or the title) closes any open finding.
                flush_finding()
                if text:
                    cur_h1 = text
                    sections.setdefault(cur_h1, [])
                continue
            # A deeper heading inside the Findings section starts a new finding.
            if _is_findings_section(cur_h1) and lvl is not None and lvl >= 2 and text:
                flush_finding()
                cur_finding = {"title": text, "parts": []}
                continue
            if not text:
                continue
            if cur_finding is not None:
                cur_finding["parts"].append(text)
            elif cur_h1:
                sections[cur_h1].append(text)
        else:  # Table
            ttext = _table_to_text(block)
            if not ttext.strip():
                continue
            first_row = ttext.split("\n", 1)[0]
            if mitre_table is None and _looks_like_mitre_header(first_row):
                mitre_table = ttext
            tagged = f"[TABLE]\n{ttext}\n[/TABLE]"
            if cur_finding is not None:
                cur_finding["parts"].append(tagged)
            elif cur_h1:
                sections[cur_h1].append(tagged)
    flush_finding()

    sections_text = {k: "\n".join(v).strip() for k, v in sections.items()}
    # Drop a likely table-of-contents echo: a "Findings" finding with no body that
    # duplicates a real finding title can appear if TOC entries were mis-styled.
    findings = [f for f in findings if f["title"]]

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
