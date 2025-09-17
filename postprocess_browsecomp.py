#!/usr/bin/env python3
"""
Post-process BrowseComp allresults.json to recompute accuracy excluding
empty/placeholder responses (e.g., after running out of credits).

Usage:
  python -m simple_evals.postprocess_browsecomp --latest
  python -m simple_evals.postprocess_browsecomp --file /tmp/browsecomp_*_allresults.json
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
from statistics import mean

from . import common  # reuse HTML report utilities

def extract_score_from_html(html: str) -> float | None:
    """Return per-example score as 0.0/1.0 from the HTML block.

    The per-example HTML prints "Score: True/False" (bool) or sometimes numeric.
    """
    m = re.search(r"Score:\s*(True|False|[0-9]+(?:\.[0-9]+)?)", html)
    if not m:
        return None
    token = m.group(1)
    if token in ("True", "False"):
        return 1.0 if token == "True" else 0.0
    try:
        return float(token)
    except Exception:
        return None


def is_empty_assistant(convo: list[dict]) -> bool:
    """Detect placeholder/empty assistant outputs.

    We consider an example empty if the last assistant message has no content
    ("" or whitespace) or is the known placeholder.
    """
    if not convo:
        return True
    last = convo[-1]
    content = (last.get("content") or "").strip()
    if not content:
        return True
    if content.startswith("No response (bad request)"):
        return True
    return False


def main() -> None:
    ap = argparse.ArgumentParser(description="Post-process BrowseComp results to exclude empty responses")
    ap.add_argument("--file", help="Path to *_allresults.json produced by simple_evals")
    ap.add_argument("--latest", action="store_true", help="Use the latest /tmp/browsecomp_*_allresults.json")
    args = ap.parse_args()

    result_file = args.file
    if args.latest and not result_file:
        candidates = sorted(glob.glob(os.path.join("/tmp", "browsecomp_*_allresults.json")))
        if not candidates:
            raise SystemExit("No /tmp/browsecomp_*_allresults.json files found")
        result_file = candidates[-1]
    if not result_file:
        raise SystemExit("Must provide --file or --latest")

    with open(result_file, "r") as fh:
        data = json.load(fh)

    htmls: list[str] = data.get("htmls", [])
    convos: list[list[dict]] = data.get("convos", [])

    total = len(htmls)
    if len(convos) != total:
        print(f"Warning: htmls ({len(htmls)}) and convos ({len(convos)}) length mismatch; proceeding with min length")
    n = min(len(htmls), len(convos))

    kept_scores: list[float] = []
    kept_htmls: list[str] = []  # html blocks to include in postprocessed report
    skipped = 0
    for i in range(n):
        if is_empty_assistant(convos[i]):
            skipped += 1
            continue
        score = extract_score_from_html(htmls[i])
        if score is None:
            # if score is missing, conservatively skip this item from recompute
            skipped += 1
            continue
        kept_scores.append(score)
        kept_htmls.append(htmls[i])

    kept = len(kept_scores)
    recomputed_acc = mean(kept_scores) if kept_scores else 0.0

    original_score = data.get("score")
    summary = {
        "file": result_file,
        "original_aggregate_score": original_score,
        "total_examples": total,
        "kept_examples": kept,
        "skipped_examples": skipped,
        "recomputed_accuracy_excluding_empty": recomputed_acc,
    }
    print(json.dumps(summary, indent=2))

    # Write a postprocessed HTML report next to the JSON
    out_html = os.path.splitext(result_file.replace("_allresults", "_postprocessed"))[0] + ".html"
    # Prepend a small summary block to the examples
    header_block = (
        f"<h2>Postprocessed Report</h2>"
        f"<p>Source JSON: {os.path.basename(result_file)}</p>"
        f"<p>Total: {total} | Kept: {kept} | Skipped: {skipped} | Accuracy (kept): {recomputed_acc:.3f}</p>"
    )
    html_content = common.make_report_from_example_htmls([header_block] + kept_htmls)
    with open(out_html, "w") as fh:
        fh.write(html_content)
    print(json.dumps({"postprocessed_html": out_html}, indent=2))


if __name__ == "__main__":
    main()


