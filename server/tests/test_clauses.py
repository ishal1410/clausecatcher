"""Tests for server/clauses.py (extract_clauses / load_demo_contract).

Run: python -m unittest discover -s server/tests -t . (from repo root), or
python server/tests/test_clauses.py directly.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from server.clauses import ClauseExtractionError, extract_clauses, load_demo_contract

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
REAL_PDF = REPO_ROOT / "spikes" / "harness" / "fake_contract.pdf"
REAL_JSON = REPO_ROOT / "spikes" / "harness" / "fake_contract.json"


class RealDemoContractTest(unittest.TestCase):
    """extract_clauses() on the actual demo PDF must match the checked-in JSON."""

    def test_matches_fake_contract_json_exactly(self) -> None:
        expected = json.loads(REAL_JSON.read_text(encoding="utf-8"))["clauses"]
        actual = extract_clauses(REAL_PDF.read_bytes())
        self.assertEqual(actual, expected)

    def test_load_demo_contract_matches_json(self) -> None:
        expected = json.loads(REAL_JSON.read_text(encoding="utf-8"))["clauses"]
        self.assertEqual(load_demo_contract(), expected)


class MultiPageFixtureTest(unittest.TestCase):
    """Heading style variety, wrapped body incl. across a page break, a
    repeated header line that must not leak, nested numbering, ignored
    preamble -- all in one fixture (server/tests/fixtures/multi_page.pdf)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.clauses = extract_clauses((FIXTURES / "multi_page.pdf").read_bytes())
        cls.by_section = {c["section_number"]: c for c in cls.clauses}

    def test_finds_exactly_the_five_numbered_clauses(self) -> None:
        self.assertEqual(
            sorted(self.by_section.keys()), ["3", "3.1", "3.2", "4.2", "4.3"]
        )

    def test_plain_heading_style(self) -> None:
        c = self.by_section["3"]
        self.assertEqual(c["title"], "General Terms")
        self.assertEqual(c["literal_text"], "This section governs general terms of engagement.")

    def test_body_wraps_across_a_page_break(self) -> None:
        c = self.by_section["3.1"]
        self.assertEqual(c["title"], "Pricing & Seat Cap")
        self.assertEqual(
            c["literal_text"],
            "Flat $48,000 up to 50 seats; extra seats need signed written "
            "amendment that continues onto the next page without any "
            "verbal discounting allowed at all.",
        )

    def test_nested_subsection(self) -> None:
        c = self.by_section["3.2"]
        self.assertEqual(c["title"], "Seat Overage")
        self.assertEqual(c["literal_text"], "Overage seats billed monthly at the standard per-seat rate.")

    def test_section_prefix_and_em_dash_heading_style(self) -> None:
        c = self.by_section["4.2"]
        self.assertEqual(c["title"], "Renewal")
        self.assertEqual(
            c["literal_text"],
            "Auto-renews 12 months unless written notice 60 days before "
            "term ends; no mid-term termination is permitted.",
        )

    def test_trailing_dot_heading_style(self) -> None:
        c = self.by_section["4.3"]
        self.assertEqual(c["title"], "Termination for Convenience")
        self.assertEqual(c["literal_text"], "Either party may terminate with 90 days prior written notice.")

    def test_repeated_header_does_not_leak_into_any_clause_text(self) -> None:
        for c in self.clauses:
            self.assertNotIn("ACME CORP", c["literal_text"])
            self.assertNotIn("ACME CORP", c["title"])

    def test_preamble_before_first_heading_is_ignored(self) -> None:
        for c in self.clauses:
            self.assertNotIn("fixture preamble", c["literal_text"])
            self.assertNotIn("fixture preamble", c["title"])


class ErrorCasesTest(unittest.TestCase):
    def test_not_pdf_bytes_raises(self) -> None:
        with self.assertRaises(ClauseExtractionError):
            extract_clauses(b"this is definitely not a pdf file")

    def test_no_text_layer_raises_with_explanatory_message(self) -> None:
        pdf_bytes = (FIXTURES / "no_text_layer.pdf").read_bytes()
        with self.assertRaises(ClauseExtractionError) as ctx:
            extract_clauses(pdf_bytes)
        self.assertIn("text layer", str(ctx.exception).lower())

    def test_text_but_no_numbered_clauses_raises(self) -> None:
        pdf_bytes = (FIXTURES / "no_clauses.pdf").read_bytes()
        with self.assertRaises(ClauseExtractionError):
            extract_clauses(pdf_bytes)

    def test_oversized_pdf_raises(self) -> None:
        oversized = b"%PDF-1.4\n" + b"0" * (5 * 1024 * 1024 + 1)
        with self.assertRaises(ClauseExtractionError):
            extract_clauses(oversized)


if __name__ == "__main__":
    unittest.main()
