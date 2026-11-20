from django.utils.translation import gettext
"""Read uploads into ordered, citable sections before LangChain indexes them."""

from io import BytesIO
from pathlib import Path
import subprocess
from threading import Lock
import unicodedata
from zipfile import ZipFile

import pymupdf
from docx import Document as WordDocument
from docx.oxml.ns import qn
from docx.table import Table
from openpyxl import load_workbook
from PIL import Image, ImageOps


MAX_UPLOAD = 20 * 1024 * 1024
MAX_CHARS = 600_000
MAX_PIXELS = 24_000_000
FORMATS = {".docx", ".xlsx", ".pdf", ".txt", ".png", ".jpg", ".jpeg"}
_pdf_lock = Lock()  # MuPDF documents must not be used by concurrent threads.


def _ocr(image):
    if image.width * image.height > MAX_PIXELS:
        raise ValueError(gettext("تصویر برای پردازش بیش از حد بزرگ است."))
    image = ImageOps.exif_transpose(image).convert("RGB")
    stream = BytesIO()
    image.save(stream, format="PNG")
    try:
        # A sparse scan sometimes needs the single-block layout instead of automatic segmentation.
        for mode in ("3", "6"):
            result = subprocess.run(
                ["tesseract", "stdin", "stdout", "-l", "fas+eng", "--dpi", "300", "--psm", mode],
                input=stream.getvalue(), capture_output=True, timeout=45, check=True,
            )
            text = result.stdout.decode("utf-8").strip()
            if text:
                return text.replace("\u200e", "").replace("\u200f", "")
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError(gettext("خواندن تصویر ناموفق بود. نصب Tesseract و زبان‌های fas و eng را بررسی کنید.")) from exc
    return ""


def _pdf(data):
    with _pdf_lock, pymupdf.open(stream=data, filetype="pdf") as document:
        if document.needs_pass:
            raise ValueError(gettext("برای بارگذاری، ابتدا رمز PDF را بردارید."))
        if len(document) > 100:
            raise ValueError(gettext("حداکثر تعداد صفحات PDF برابر ۱۰۰ است."))
        for page in document:
            location = f"Page {page.number + 1}"
            text = page.get_text("text").strip()
            # A page number can be selectable while the actual page is a scan.
            has_large_scan = len(text.split()) <= 4 and any(
                (pymupdf.Rect(image["bbox"]) & page.rect).get_area() > 0.6 * page.rect.get_area()
                for image in page.get_image_info()
            )
            if not any(char.isalnum() for char in text) or has_large_scan:
                # Bound the raster before allocating memory on oversized pages.
                size = page.rect
                if size.width <= 0 or size.height <= 0:
                    continue
                scale = min(3, 4096 / max(size.width, size.height))
                pixmap = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
                image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
                recognized = _ocr(image)
                if recognized:
                    text = recognized if text in recognized else (text + "\n" + recognized).strip()
                    location += " · OCR"
            yield location, unicodedata.normalize("NFKC", text)
            if text and "OCR" not in location and not has_large_scan:
                # A slide can contain selectable text beside a scanned table.
                words = page.get_text("words")
                for index, info in enumerate(page.get_image_info(), 1):
                    box = pymupdf.Rect(info["bbox"]) & page.rect
                    if box.width < 24 or box.height < 12 or any(box.contains(pymupdf.Rect(w[:4])) for w in words):
                        continue
                    scale = min(3, 4096 / max(box.width, box.height))
                    pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), clip=box, alpha=False)
                    yield f"{location} · Image {index} · OCR", _ocr(Image.frombytes("RGB", (pix.width, pix.height), pix.samples))


def _word_content(container):
    for item in container.iter_inner_content():
        if isinstance(item, Table):
            for row in item.rows:
                yield " | ".join(" ".join(_word_content(cell)) for cell in row.cells)
        else:
            if item.text.strip():
                yield item.text
            for blip in item._p.xpath(".//a:blip"):
                part = item.part.related_parts.get(blip.get(qn("r:embed")))
                if part and part.content_type in {"image/png", "image/jpeg", "image/tiff", "image/bmp"}:
                    with Image.open(BytesIO(part.blob)) as image:
                        text = _ocr(image)
                        if text:
                            yield text


def _docx(data):
    document = WordDocument(BytesIO(data))
    for number, section in enumerate(document.sections, 1):
        for label, part in [("Header", section.header), ("Footer", section.footer)]:
            if not part.is_linked_to_previous:
                yield f"{label} {number}", "\n".join(_word_content(part))
    yield "Document body", "\n\n".join(_word_content(document))


def _xlsx(data):
    # Excel may have a cached result. Keep the formula when there is no cached value.
    values = load_workbook(BytesIO(data), read_only=True, data_only=True)
    formulas = load_workbook(BytesIO(data), read_only=True, data_only=False)
    try:
        for sheet in values:
            source = formulas[sheet.title]
            if (sheet.max_row or 0) * (sheet.max_column or 0) > 200_000:
                raise ValueError(gettext("تعداد خانه‌های برگه از حد پردازش بیشتر است."))
            for number, (row, raw) in enumerate(zip(
                sheet.iter_rows(values_only=True), source.iter_rows(values_only=True)
            ), 1):
                cells = [str(a if a is not None else b) if a is not None or b is not None else ""
                         for a, b in zip(row, raw)]
                line = " | ".join(cells).strip(" |")
                if not line:
                    continue
                location = f"{sheet.title} · Row {number}"
                yield location, line
    finally:
        values.close()
        formulas.close()


def _read(data, suffix):
    if suffix in {".docx", ".xlsx"}:
        with ZipFile(BytesIO(data)) as archive:
            if sum(info.file_size for info in archive.infolist()) > 80 * 1024 * 1024:
                raise ValueError(gettext("حجم محتوای بازشده سند از حد مجاز بیشتر است."))
        return _docx(data) if suffix == ".docx" else _xlsx(data)
    if suffix == ".pdf":
        return _pdf(data)
    if suffix == ".txt":
        encoding = "utf-16" if data.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
        return [("Text", data.decode(encoding))]
    with Image.open(BytesIO(data)) as image:
        return [("Image · OCR", _ocr(image))]


def extract_sections(upload):
    """Accept a Django upload or any seekable binary file with a name."""
    suffix = Path(upload.name).suffix.lower()
    if suffix not in FORMATS:
        raise ValueError(gettext("قالب فایل پشتیبانی نمی‌شود."))
    upload.seek(0)
    data = upload.read(MAX_UPLOAD + 1)
    upload.seek(0)
    if len(data) > MAX_UPLOAD:
        raise ValueError(gettext("حجم فایل باید حداکثر ۲۰ مگابایت باشد."))
    sections = []
    length = 0
    try:
        for location, text in _read(data, suffix):
            text = text.replace("\x00", "").replace("\r\n", "\n").strip()
            if not text:
                continue
            length += len(text)
            if length > MAX_CHARS:
                raise ValueError(gettext("حجم متن استخراج‌شده از ۶۰۰٬۰۰۰ نویسه بیشتر است."))
            sections.append({"location": location, "text": text})
    except UnicodeError as exc:
        raise ValueError(gettext("فایل متنی باید با UTF-8 یا UTF-16 ذخیره شده باشد.")) from exc
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(gettext("فایل خوانده نشد. قالب، سلامت و رمزدار نبودن فایل را بررسی کنید.")) from exc
    if not sections:
        raise ValueError(gettext("متن خوانایی در این فایل پیدا نشد."))
    return sections
