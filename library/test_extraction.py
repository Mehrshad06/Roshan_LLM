"""Exercise fixture files, including the boundary between native PDF text and OCR."""

from io import BytesIO
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch
import pymupdf

from .extraction import extract_sections


SAMPLES = Path(__file__).resolve().parents[1] / "samples"


def read_sample(name):
    with (SAMPLES / name).open("rb") as upload:
        return extract_sections(upload)


class ExtractionTests(unittest.TestCase):
    def test_readable_formats(self):
        cases = {
            "fa/alefba-guide.docx": "موقعیت",
            "mixed/alefba-pilot.docx": "24 MB",
            "mixed/acceptance.xlsx": "ARC-318",
            "en/alefba-response.pdf": "recognition confidence",
            "private/reviewer-note.txt": "CEDAR-819",
        }
        for path, expected in cases.items():
            with self.subTest(path=path):
                self.assertIn(expected, " ".join(p["text"] for p in read_sample(path)))

    def test_only_scanned_pdf_page_uses_ocr(self):
        with patch("library.extraction._ocr", return_value="خواندن شیفت") as ocr:
            sections = read_sample("mixed/shift-handover.pdf")
        ocr.assert_called_once()
        self.assertEqual([s["location"] for s in sections], ["Page 1", "Page 2 · OCR"])
        self.assertIn("Archive handover", sections[0]["text"])
        self.assertIn("شیفت", sections[1]["text"])

    @unittest.skipUnless(shutil.which("tesseract"), "Tesseract is unavailable on this host")
    def test_bilingual_ocr_reads_real_scans(self):
        self.assertIn("الفبا", read_sample("fa/archive.png")[0]["text"])
        self.assertIn("SHIFT-92", read_sample("mixed/shift-handover.pdf")[1]["text"])
        self.assertIn("LANTERN-53", read_sample("mixed/transfer.jpg")[0]["text"])

    def test_page_number_does_not_hide_a_scanned_page(self):
        with pymupdf.open() as pdf:
            page = pdf.new_page(width=400, height=300)
            page.insert_image(page.rect, filename=str(SAMPLES / "fa/archive.png"), keep_proportion=False)
            page.insert_text((15, 290), "Page 4")
            upload = BytesIO(pdf.tobytes())
        upload.name = "numbered-scan.pdf"
        with patch("library.extraction._ocr", return_value="متن اسکن") as ocr:
            section = extract_sections(upload)[0]
        ocr.assert_called_once()
        self.assertIn("Page 4", section["text"])
        self.assertIn("متن اسکن", section["text"])

    def test_reject_empty_or_corrupt_uploads(self):
        for name, content in [("empty.txt", b" \n"), ("broken.pdf", b"bad"), ("bad.zip", b"bad")]:
            with self.subTest(name=name):
                upload = BytesIO(content)
                upload.name = name
                with self.assertRaises(ValueError):
                    extract_sections(upload)
