#!/usr/bin/env python3
"""Generate the taxonomy diagrams from the paper list in README.md.

README.md is the single source of truth. This script reads the section headings
and the paper tables under them, and writes img/static_papers.mermaid and
img/dynamic_papers.mermaid. The SVGs are rendered from those by mermaid-cli,
which the GitHub Actions workflow runs on every push that touches README.md.

Usage:
    python tools/build_tree.py             # regenerate the .mermaid sources
    python tools/build_tree.py --check     # exit 1 if they are out of date
"""

import argparse
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
ALIASES = ROOT / "tools" / "title_aliases.json"
OUT = {
    "3": ROOT / "img" / "static_papers.mermaid",
    "4": ROOT / "img" / "dynamic_papers.mermaid",
}
ROOT_LABEL = {"3": "3. STATIC SCENES", "4": "4. DYNAMIC SCENES"}

# "## 3.STATIC", "### 3.1. Parameter Compression", "## 3.2. Restructuring Compression",
# "### 3.1.1. Pruning".  The heading level is inconsistent in the README, so the
# number of dot-separated parts decides the depth, not the number of hashes.
HEADING = re.compile(r"^#{2,4}\s*(\d+(?:\.\d+)*)\.?\s*(.*)$")

ROW = re.compile(
    r"<tr>\s*"
    r'<td align="left">\s*'
    r'<a href="([^"]+)">\s*'
    r"(.+?)\s*"
    r"</a>\s*"
    r"</td>\s*"
    r'<td align="center">(.*?)</td>\s*'
    r'<td align="center">(.*?)</td>',
    re.S,
)

MAX_LABEL = 34

# a category with many papers is split into columns so the diagram stays readable
COLUMN_HEIGHT = 12


def parse_readme(text):
    """Return [(number, title, [paper, ...]), ...] for every heading, in order."""
    lines = text.split("\n")
    marks = []
    for i, line in enumerate(lines):
        m = HEADING.match(line)
        if m and m.group(1)[0] in OUT:
            marks.append((i, m.group(1).rstrip("."), m.group(2).strip()))

    sections = []
    for idx, (line_no, number, title) in enumerate(marks):
        end = marks[idx + 1][0] if idx + 1 < len(marks) else len(lines)
        body = "\n".join(lines[line_no + 1 : end])
        papers = [
            {
                "url": m.group(1).strip(),
                "title": re.sub(r"\s+", " ", m.group(2)).strip(),
                "venue": m.group(3).strip(),
                "year": m.group(4).strip(),
            }
            for m in ROW.finditer(body)
        ]
        sections.append({"number": number, "title": title, "papers": papers})
    return sections


def shorten(title, aliases):
    """Diagram labels have to stay narrow, so use a curated short name where we have one."""
    if title in aliases:
        return aliases[title]
    head = title.split(":")[0].strip()
    if len(head) <= MAX_LABEL:
        return head
    words, kept = head.split(), []
    for w in words:
        if len(" ".join(kept + [w])) > MAX_LABEL - 3:
            break
        kept.append(w)
    return (" ".join(kept) if kept else head[: MAX_LABEL - 3]) + "..."


def escape(label):
    """Mermaid labels are emitted quoted, so only quotes and braces need care."""
    return (
        label.replace('"', "#quot;")
        .replace("{", "#123;")
        .replace("}", "#125;")
        .replace("\\", "/")
    )


def build(kind, sections, aliases):
    top = kind  # "3" or "4"
    mids = [s for s in sections if re.fullmatch(rf"{top}\.\d+", s["number"])]
    leaves = [s for s in sections if re.fullmatch(rf"{top}\.\d+\.\d+", s["number"])]

    out = ["graph TB", f'    Root["{ROOT_LABEL[top]}"]', ""]
    mid_ids, leaf_ids, paper_ids = {}, {}, []

    out.append("    %% Main Categories")
    for i, mid in enumerate(mids, 1):
        mid_id = f"C{i}"
        mid_ids[mid["number"]] = mid_id
        out.append(f'    Root --> {mid_id}["{escape(mid["number"])} {escape(mid["title"])}"]')
    out.append("")

    counter = 0
    for mid in mids:
        own = [s for s in leaves if s["number"].startswith(mid["number"] + ".")]
        if not own:
            continue
        out.append(f'    %% {mid["title"]} subcategories')
        for leaf in own:
            counter += 1
            leaf_id = f"S{counter}"
            leaf_ids[leaf["number"]] = leaf_id
            n = len(leaf["papers"])
            noun = "paper" if n == 1 else "papers"
            label = f'{leaf["number"]} {leaf["title"]}<br/>{n} {noun}'
            out.append(f'    {mid_ids[mid["number"]]} --> {leaf_id}["{escape(label)}"]')
        out.append("")

    seq = 0
    for leaf in leaves:
        if leaf["number"] not in leaf_ids or not leaf["papers"]:
            continue
        out.append(f'    %% {leaf["number"]} {leaf["title"]}')
        papers = leaf["papers"]
        columns = [
            papers[i : i + COLUMN_HEIGHT] for i in range(0, len(papers), COLUMN_HEIGHT)
        ]
        for column in columns:
            prev = leaf_ids[leaf["number"]]
            for paper in column:
                seq += 1
                pid = f"P{seq}"
                paper_ids.append(pid)
                venue = " ".join(x for x in (paper["venue"], paper["year"]) if x)
                label = f'{shorten(paper["title"], aliases)}<br/>{venue}'
                out.append(f'    {prev} --- {pid}["{escape(label)}"]')
                prev = pid
        out.append("")

    out += [
        "    %% Styling",
        "    classDef rootClass fill:#e1f5ff,stroke:#0288d1,stroke-width:3px,color:#000",
        "    classDef categoryClass fill:#fff9c4,stroke:#f57c00,stroke-width:2px,color:#000",
        "    classDef subcategoryClass fill:#f3e5f5,stroke:#7b1fa2,stroke-width:2px,color:#000",
        "    classDef paperClass fill:#e8f5e9,stroke:#388e3c,stroke-width:1px,color:#000",
        "",
        "    class Root rootClass",
    ]
    if mid_ids:
        out.append("    class " + ",".join(mid_ids.values()) + " categoryClass")
    if leaf_ids:
        out.append("    class " + ",".join(leaf_ids.values()) + " subcategoryClass")
    for i in range(0, len(paper_ids), 20):
        out.append("    class " + ",".join(paper_ids[i : i + 20]) + " paperClass")
    out += [
        "",
        "    %% Link styling for dark mode visibility",
        "    linkStyle default stroke:#666,stroke-width:2px",
        "",
    ]
    return "\n".join(out), len(paper_ids)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="fail if the diagrams are stale")
    args = ap.parse_args()

    text = README.read_text(encoding="utf-8")
    aliases = json.loads(ALIASES.read_text(encoding="utf-8")) if ALIASES.exists() else {}
    sections = parse_readme(text)

    # independent count: every <tr> except the one inside each <thead>
    expected = text.count("<tr>") - text.count("<thead>")
    total_rows = len(ROW.findall(text))
    if total_rows != expected:
        print(
            f"ERROR: {expected} table rows in README.md but only {total_rows} parsed cleanly",
            file=sys.stderr,
        )
        return 2
    stale = []
    grand = 0
    for kind, path in OUT.items():
        content, n = build(kind, sections, aliases)
        grand += n
        leaves = [s for s in sections if re.fullmatch(rf"{kind}\.\d+\.\d+", s["number"])]
        print(f"{ROOT_LABEL[kind]}: {len(leaves)} categories, {n} entries")
        for leaf in leaves:
            print(f'  {leaf["number"]:<8} {leaf["title"]:<42} {len(leaf["papers"]):>3}')
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != content:
                stale.append(path.name)
        else:
            path.write_text(content, encoding="utf-8")
            print(f"  -> {path.relative_to(ROOT)}")

    # every table row in the README has to land in exactly one diagram
    if grand != total_rows:
        print(f"ERROR: README has {total_rows} rows but the diagrams cover {grand}", file=sys.stderr)
        return 2
    print(f"OK: {grand} entries, matching all {total_rows} rows in README.md")

    if stale:
        print("STALE: " + ", ".join(stale), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
