"""Clause extraction from PDF contracts.

Contract (consumed by server/main.py):
    extract_clauses(pdf_bytes: bytes) -> list[dict]
        keys: section_number (str, e.g. "3.1"), title (str),
        literal_text (str, whitespace-normalized, otherwise EXACT PDF words)
        raises ClauseExtractionError for unreadable/encrypted/empty PDFs or
        when no numbered clauses are found.
    async extract_clauses_safe(pdf_bytes, timeout_s=10.0) -> list[dict]
        what the upload route calls: same result, but parsed in a separate
        memory-capped process with a timeout so a hostile PDF can't freeze
        the event loop or OOM the box. Errors are generic, details logged.
    load_demo_contract() -> list[dict]
        reads spikes/harness/fake_contract.json (path resolved from this file).

Heuristic (ponytail: simplest thing that clears the fixtures):
    1. pdfplumber pulls text per page, one string per source line.
    2. A line whose normalized form appears on >=2 distinct pages is a
       running header/footer and is dropped everywhere it occurs.
    3. A heading line matches _HEADING_RE at the START of the line:
       optional "Section " prefix, a dotted number ("3", "3.1", "3.1.2"),
       optional trailing ".", then a separator and a title. Every line
       until the next heading is that clause's body (whitespace-joined).

    Ceiling: this is a start-of-line regex, not font/layout analysis, so a
    body sentence that happens to *open* a line with "<number><space>word"
    (e.g. a stray "12 months later, ...") would be misread as a new
    heading. A real fix needs pdfplumber word/char attributes (font size,
    bold) to distinguish headings from body text; out of scope here.
"""
from __future__ import annotations

import asyncio
import io
import json
import logging
import multiprocessing
import re
import sys
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from pathlib import Path

import pdfplumber

MAX_PDF_BYTES = 5 * 1024 * 1024
MAX_PAGES = 50
WORKER_MEM_LIMIT_BYTES = 300 * 1024 * 1024  # RLIMIT_AS for the parse worker (Linux only)

logger = logging.getLogger("clausecatcher")

# number: "3", "3.1", "3.1.2" ... optional trailing "." ... then either a
# dash/colon/em-dash separator or plain whitespace before the title. The
# mandatory whitespace/dot right after the number is what keeps this from
# matching body text like "30-day recoverable archive..." (no space/dot
# after the "30") or "24/7 requires..." (no space/dot after the "24").
_HEADING_RE = re.compile(r"^(?:Section\s+)?(\d+(?:\.\d+)*)\.?\s+[-—:]?\s*(\S.*)$")
_WS_RE = re.compile(r"\s+")


class ClauseExtractionError(Exception):
    """Raised when a PDF cannot be turned into a clause list."""


def _normalize(text: str) -> str:
    return _WS_RE.sub(" ", text).strip()


def _repeated_lines(pages_lines: list[list[str]]) -> set[str]:
    """Lines whose text appears on >=2 distinct pages -> header/footer."""
    seen_on: dict[str, set[int]] = {}
    for page_idx, lines in enumerate(pages_lines):
        for line in set(l.strip() for l in lines if l.strip()):
            seen_on.setdefault(line, set()).add(page_idx)
    return {line for line, pages in seen_on.items() if len(pages) >= 2}


def extract_clauses(pdf_bytes: bytes) -> list[dict]:
    if not isinstance(pdf_bytes, (bytes, bytearray)):
        raise ClauseExtractionError("pdf_bytes must be bytes")
    if len(pdf_bytes) > MAX_PDF_BYTES:
        raise ClauseExtractionError("PDF exceeds 5 MB size limit")

    pages_lines: list[list[str]] = []
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            if len(pdf.pages) > MAX_PAGES:
                raise ClauseExtractionError(f"PDF has more than {MAX_PAGES} pages")
            for page in pdf.pages:
                pages_lines.append((page.extract_text() or "").split("\n"))
                page.close()  # drop per-page object cache as we go
    except ClauseExtractionError:
        raise
    except Exception as exc:  # any parse/decrypt/open failure -> our error type
        # library text stays in the server log, never in the client message
        logger.warning("PDF parse failed: %r", exc)
        raise ClauseExtractionError("unreadable PDF") from exc

    if not any(line.strip() for lines in pages_lines for line in lines):
        raise ClauseExtractionError("PDF has no text layer (empty or scanned image)")

    header_footer = _repeated_lines(pages_lines)

    clauses: list[dict] = []
    current: dict | None = None
    for lines in pages_lines:
        for raw_line in lines:
            line = raw_line.strip()
            if not line or line in header_footer:
                continue
            match = _HEADING_RE.match(line)
            if match:
                if current is not None:
                    clauses.append(
                        {
                            "section_number": current["section_number"],
                            "title": current["title"],
                            "literal_text": _normalize(" ".join(current["body"])),
                        }
                    )
                current = {
                    "section_number": match.group(1),
                    "title": _normalize(match.group(2)),
                    "body": [],
                }
            elif current is not None:
                current["body"].append(line)
    if current is not None:
        clauses.append(
            {
                "section_number": current["section_number"],
                "title": current["title"],
                "literal_text": _normalize(" ".join(current["body"])),
            }
        )

    if not clauses:
        raise ClauseExtractionError("no numbered clauses found in PDF")

    return clauses


def _worker_init() -> None:
    if sys.platform != "win32":
        import resource

        resource.setrlimit(
            resource.RLIMIT_AS, (WORKER_MEM_LIMIT_BYTES, WORKER_MEM_LIMIT_BYTES)
        )


_pool: ProcessPoolExecutor | None = None


def _get_pool() -> ProcessPoolExecutor:
    global _pool
    if _pool is None:
        _pool = ProcessPoolExecutor(
            max_workers=1,
            mp_context=multiprocessing.get_context("spawn"),
            initializer=_worker_init,
        )
    return _pool


def _kill_pool(pool: ProcessPoolExecutor) -> None:
    """Hard-stop a pool whose worker is hung/dead; next call spawns a fresh one."""
    global _pool
    if _pool is pool:
        _pool = None
    # ponytail: private _processes; Python 3.14 has pool.kill_workers() instead
    for proc in list((getattr(pool, "_processes", None) or {}).values()):
        try:
            proc.kill()
        except Exception:
            pass
    pool.shutdown(wait=False, cancel_futures=True)


async def extract_clauses_safe(pdf_bytes: bytes, timeout_s: float = 10.0) -> list[dict]:
    """extract_clauses() in a 1-worker spawn process, capped by timeout_s.

    ponytail: one worker is shared, so concurrent uploads queue (queue time
    counts toward the timeout) and a kill fails any in-flight neighbour with
    a generic error. Fine for a single-demo box; per-request processes if not.
    """
    if not isinstance(pdf_bytes, (bytes, bytearray)) or not bytes(
        pdf_bytes[:1024]
    ).lstrip().startswith(b"%PDF-"):
        raise ClauseExtractionError("unreadable PDF")

    pool = _get_pool()
    loop = asyncio.get_running_loop()
    try:
        return await asyncio.wait_for(
            loop.run_in_executor(pool, extract_clauses, bytes(pdf_bytes)), timeout_s
        )
    except ClauseExtractionError:
        raise
    except (asyncio.TimeoutError, BrokenProcessPool) as exc:
        logger.warning("PDF parse worker timed out or died (%r); restarting it", exc)
        _kill_pool(pool)
        raise ClauseExtractionError("PDF could not be processed (too slow or too large)") from None
    except Exception as exc:  # MemoryError from the rlimit, pickling, etc.
        logger.warning("PDF parse worker failed: %r", exc)
        raise ClauseExtractionError("unreadable PDF") from None


def load_demo_contract() -> list[dict]:
    path = Path(__file__).resolve().parent.parent / "spikes" / "harness" / "fake_contract.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["clauses"]
