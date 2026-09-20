"""fix_deck.py - correct the retracted numbers in ClauseCatcher.pptx.

Every text asset in the repo was corrected against docs/submission/TRUTH_AUDIT.md,
but the deck was not: it still shows the "~2 s" and "~78 ms" figures the audit
grades WRONG and MISLEADING, and "136 server tests" (now 151). The video shows
~5 s of real latency on screen, so the deck currently contradicts the demo.

Each replacement below cites the audit row it satisfies. Big-stat strings stay
about as wide as what they replace so the hand-built text boxes do not reflow;
the range goes in the caption underneath, which has room.

    pip install python-pptx
    python tools/fix_deck.py            # rewrites the pptx in place
    python tools/fix_deck.py --check    # exits 1 if any target text is missing

Re-export ClauseCatcher.pdf from the rewritten pptx afterwards (PowerPoint:
File > Export > Create PDF/XPS); the PDF is what actually gets uploaded.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pptx import Presentation

ROOT = Path(__file__).resolve().parents[1]
DECK = ROOT / "docs/submission/ClauseCatcher.pptx"

# (exact current paragraph text, replacement, audit row)
EDITS = [
    # row 1: every logged alert is 4.0 s or slower
    ("§3.1 flagged in ~2 s", "§3.1 flagged in ~5 s", "TRUTH_AUDIT #1"),
    # row 2: same figure on the results slide, plus the range in the caption
    ("~2 s", "~5 s", "TRUTH_AUDIT #2"),
    ("sentence end to alert", "sentence end to alert (4–6.5 s, five alerts)", "TRUTH_AUDIT #2"),
    # row 8: 78 ms is the fastest of eight probe steps, not the typical one
    ("~78 ms", "~0.2 s", "TRUTH_AUDIT #8"),  # "~200 ms" is too wide for the stat box and breaks mid-word
    ("speak request to first audio", "speak request to first audio (78–890 ms)", "TRUTH_AUDIT #8"),
    # row 17: the check grades the agent's own transcript, not the audio
    ("spoken vs. contract similarity", "agent transcript vs. clause text", "TRUTH_AUDIT #17"),
    # row 9: measured $0.0755 / $0.1466 / $0.1535, never $0.12
    ("~$0.12", "~$0.15", "TRUTH_AUDIT #9"),
    ("API usage, full demo call", "API usage, full call ($0.08–$0.15)", "TRUTH_AUDIT #9"),
    ("~$0.12 API usage per demo call", "$0.08–$0.15 API usage per call", "TRUTH_AUDIT #9"),
    # the eval is the strongest technical result in the project and the deck
    # never mentioned it (docs/evidence/claim_check_eval_20260918.json)
    ("151 server tests passing",
     "14/14 contradictions caught, 0 false alarms; 151 server tests passing",
     "JUDGE_REVIEW 2026-09-20 §2.2"),
    # (the earlier "136 server tests passing" -> "151" rule retired once the
    # eval rule above took over that paragraph; 136 appears in no deck now)
    # JUDGE_REVIEW 2026-09-20: this contradicts README.md:18, which says the
    # clause request is "a dropdown, not a spoken question", and the video at
    # 2:09 shows the dropdown. One caught overclaim discounts every other
    # number on a slide titled MEASURED, NOT PROJECTED.
    ("A monitor's spoken question about §4.2 answered correctly by voice",
     "A monitor's clause request for §4.2, picked from the rail, answered by voice",
     "JUDGE_REVIEW 2026-09-20 §2.1"),
    # underclaim: the browser path is verified 17/17 (CHECKLIST item 14); what
    # is actually untested is physical microphone hardware
    ("Browser-mic path, hardened end to end",
     "Physical-mic hardware (browser path verified 17/17)",
     "JUDGE_REVIEW 2026-09-20 §2.7"),
    # the deck now cites more than one run, so the subtitle has to agree
    ("One live end-to-end run, real connections", "Live end-to-end runs, real connections",
     "TRUTH_AUDIT #1,2,9"),
    # the numbers now span three runs, so stop dating them to one
    ("Run of 2026-09-15: real AssemblyAI Streaming STT, Voice Agent and Gemini connections, "
     "scripted rep lines fed through the pipeline.",
     "Runs of 2026-09-15 to 2026-09-17: real AssemblyAI Streaming STT, Voice Agent and Gemini "
     "connections, scripted rep lines fed through the pipeline.",
     "TRUTH_AUDIT #1,2,9"),
]


def paragraphs(prs):
    for slide_no, slide in enumerate(prs.slides, 1):
        for shape in slide.shapes:
            if not shape.has_text_frame:
                continue
            for para in shape.text_frame.paragraphs:
                yield slide_no, para


def set_text(para, new: str) -> None:
    """Replace a paragraph's text, keeping the first run's formatting."""
    runs = para.runs
    runs[0].text = new
    for run in runs[1:]:
        run.text = ""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="report only, do not write")
    ap.add_argument("--deck", default=str(DECK))
    args = ap.parse_args()

    prs = Presentation(args.deck)
    hits = {old: 0 for old, _, _ in EDITS}
    for slide_no, para in paragraphs(prs):
        text = "".join(r.text for r in para.runs)
        for old, new, why in EDITS:
            if text.strip() == new:  # already applied; rerunning is a no-op, not a failure
                hits[old] += 1
                break
            if text.strip() == old:
                hits[old] += 1
                print(f"slide {slide_no}: {old!r} -> {new!r}   ({why})")
                if not args.check:
                    set_text(para, new)
                break

    # An edit can chain onto an earlier one (136 -> 151 -> 151 + eval numbers),
    # so a rule whose `old` never matched is still satisfied if its `new` text
    # is somewhere in the deck.
    final = {"".join(r.text for r in para.runs).strip() for _, para in paragraphs(prs)}
    for old, new, _why in EDITS:
        if hits[old] == 0 and new.strip() in final:
            hits[old] += 1

    missing = [old for old, n in hits.items() if n == 0]
    if missing:
        print("\nNOT FOUND (deck already changed, or the text differs):", file=sys.stderr)
        for old in missing:
            print(f"  {old!r}", file=sys.stderr)
        sys.exit(1)

    if args.check:
        print(f"\ncheck only: {sum(hits.values())} paragraphs would change")
        return
    prs.save(args.deck)
    print(f"\nwrote {args.deck} - {sum(hits.values())} paragraphs changed")
    print("Now re-export ClauseCatcher.pdf from it.")


if __name__ == "__main__":
    main()
