"""Hostile-PDF tests for server/clauses.py:extract_clauses_safe (DoS guards).

PDFs are built from raw bytes here so no extra dependency is needed.
"""
from __future__ import annotations

import asyncio
import unittest
from pathlib import Path

from server.clauses import (
    MAX_PAGES,
    ClauseExtractionError,
    extract_clauses,
    extract_clauses_safe,
    load_demo_contract,
)

REAL_PDF = Path(__file__).resolve().parents[2] / "spikes" / "harness" / "fake_contract.pdf"


def _pdf_with_shared_content(pages: int) -> bytes:
    """`pages` pages that all point at ONE content stream (the reported bomb shape)."""
    content = b"BT /F1 12 Tf 72 720 Td (1. Term) Tj ET"
    kids = " ".join(f"{4 + i} 0 R" for i in range(pages))
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{kids}] /Count {pages} >>".encode(),
        b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream",
    ] + [
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 3 0 R "
        b"/Resources << /Font << /F1 << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> >> >> >>"
    ] * pages
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    return bytes(out)


class HostilePdfTest(unittest.TestCase):
    def test_non_pdf_bytes_rejected_before_parsing(self) -> None:
        with self.assertRaises(ClauseExtractionError) as ctx:
            asyncio.run(extract_clauses_safe(b"<html>not a pdf</html>"))
        self.assertEqual(str(ctx.exception), "unreadable PDF")

    def test_too_many_pages_rejected(self) -> None:
        pdf = _pdf_with_shared_content(MAX_PAGES + 1)
        with self.assertRaises(ClauseExtractionError) as ctx:
            extract_clauses(pdf)
        self.assertIn("more than 50 pages", str(ctx.exception))
        with self.assertRaises(ClauseExtractionError) as ctx:
            asyncio.run(extract_clauses_safe(pdf))
        self.assertIn("more than 50 pages", str(ctx.exception))

    def test_under_page_cap_still_parses(self) -> None:
        self.assertEqual(extract_clauses(_pdf_with_shared_content(1))[0]["section_number"], "1")

    def test_library_error_text_not_leaked(self) -> None:
        with self.assertRaises(ClauseExtractionError) as ctx:
            extract_clauses(b"%PDF-1.4\ngarbage that is not a pdf body")
        self.assertEqual(str(ctx.exception), "unreadable PDF")

    def test_timeout_raises_then_next_call_recovers(self) -> None:
        pdf = REAL_PDF.read_bytes()

        async def run() -> None:
            with self.assertRaises(ClauseExtractionError):
                await extract_clauses_safe(pdf, timeout_s=0.001)
            # worker was killed; a fresh one must serve the next request
            self.assertEqual(await extract_clauses_safe(pdf, timeout_s=60), load_demo_contract())

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
