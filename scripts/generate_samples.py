"""Rebuild the demo files with Python: python scripts/generate_samples.py"""

from html import escape
import json
import os
from pathlib import Path
import unicodedata

import pymupdf
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter


ROOT = Path(__file__).resolve().parents[1] / "samples"
TAG = "[داده آزمایشی / Test Data]"
SITE = "https://www.roshan-ai.ir/"
ALEFBA = "https://www.roshan-ai.ir/docs/alefba/"
HAZM = "https://github.com/roshan-research/hazm"

# Single-language files contain public information only. All invented facts live
# in the mixed files so the bilingual label does not interrupt monolingual examples.
FILES = {
    "fa/alefba-guide.docx": ("راهنمای ورودی و خروجی الفبا", ALEFBA, [
        "الفبا برای خواندن نوشته در تصویر اسناد به کار می‌رود. این ابزار نوشته‌های فارسی، انگلیسی و عربی را تشخیص می‌دهد.",
        "در خروجی، متن هر صفحه به بندها و سطرها تقسیم می‌شود. می‌توان جای هر سطر را با موقعیت آن در تصویر مطابقت داد.",
        "برای جستجو در یک بایگانی تصویری می‌توان نسخهٔ قابل جستجوی سند را دریافت کرد.",
    ]),
    "fa/harf-scan.pdf": ("تبدیل گفتار با حرف", SITE, [
        "حرف سامانهٔ تبدیل گفتار به متن روشن است.",
        "متن پیاده‌شده را می‌توان جستجو و ویرایش کرد.",
    ]),
    "fa/products.xlsx": ("فهرست کاربرد محصولات روشن", SITE, [
        ["محصول", "نوع ورودی", "کاربرد"],
        ["الفبا", "تصویر سند", "بازیابی نوشته از تصویر"],
        ["حرف", "گفتار", "تبدیل صدا به متن ویرایش‌پذیر"],
        ["هضم", "نوشته فارسی", "آماده‌سازی و پاک‌سازی متن"],
    ]),
    "fa/fahm-note.txt": ("پرسش از سند با فهم", SITE, [
        "فهم برای بررسی اسناد با مدل‌های زبانی و گفت‌وگو دربارهٔ محتوای آن‌ها طراحی شده است.",
        "الفبا متن تصویر را در اختیار کاربر می‌گذارد. فهم به کاربر امکان می‌دهد دربارهٔ متن سند بپرسد.",
    ]),
    "fa/archive.png": ("کارت بایگانی تصویری", ALEFBA, [
        "برای جستجو در بایگانی، نوشتهٔ تصویر را با الفبا بخوانید.",
        "خروجی می‌تواند موقعیت سطرها را در صفحه نشان دهد.",
    ]),
    "en/hazm-guide.docx": ("Preparing Persian text with Hazm", HAZM, [
        "Hazm is a Python toolkit for processing Persian text. Its normalizer prepares text before tokenization.",
        "Sentence tokenization separates a passage into sentences. Word tokenization works within each sentence to identify its tokens.",
        "The toolkit also supports lemmatization, part-of-speech tagging and dependency parsing.",
    ]),
    "en/alefba-response.pdf": ("Reading an Alefba response", ALEFBA, [
        "Alefba returns recognized text grouped into pages, paragraphs and lines.",
        "The box field locates a result on the source image. The probability field reports the recognition confidence.",
    ]),
    "en/hazm-steps.xlsx": ("Hazm processing steps", HAZM, [
        ["Component", "Input", "Purpose"],
        ["Normalizer", "Persian text", "Standardize the input text"],
        ["Word tokenizer", "A sentence", "Split the sentence into tokens"],
        ["Lemmatizer", "A word", "Find the lemma"],
        ["Dependency parser", "A sentence", "Identify syntactic dependencies"],
    ]),
    "en/async-reading.txt": ("Tracking an asynchronous read", ALEFBA, [
        "An asynchronous Alefba request returns its processing state and task identifiers.",
        "Use the task identifier to fetch the result when processing has finished. This separates submitting an image from retrieving its transcription.",
    ]),
    "en/token-review.jpg": ("Token review card", HAZM, [
        "Use the Hazm tokenizer to separate a Persian sentence into tokens.",
        "The lemmatizer can then recover a word's lemma.",
    ]),
    "mixed/alefba-pilot.docx": ("پایلوت الفبا برای بایگانی", ALEFBA, [
        "الفبا نوشته را از تصویر استخراج می‌کند. شرایط پایلوت زیر برای تمرین جستجو تعریف شده‌اند.",
        f"{TAG} پایلوت بایگانی الفبا با شناسه ALF-27 ورودی PNG و JPEG می‌پذیرد. سقف حجم هر فایل در این پایلوت ۲۴ مگابایت است.",
        f"{TAG} The ALF-27 archive pilot accepts PNG and JPEG images. Its upload limit is 24 MB per file.",
    ]),
    "mixed/shift-handover.pdf": ("تحویل شیفت بایگانی", "", [
        "Archive handover",
        "The scanned page carries the shift code and the handover time.",
        "تحویل شیفت بایگانی",
        TAG,
        "کد تحویل شیفت در کارت زیر درج شده است.",
        "SHIFT-92   /   17:30 UTC",
    ]),
    "mixed/acceptance.xlsx": ("دفتر ثبت آزمون پذیرش", "", [
        ["شناسه آزمون / Case", "شرح / Scenario", "نتیجه / Expected", "نوع داده / Label"],
        ["ARC-318", "بازبینی فهرست / Catalog review", "2026-04-12", TAG],
        ["OCR-614", "صف بازخوانی / Review queue", "48 pages", TAG],
        ["TAG-805", "برچسب‌گذاری / Tagging", "32 records", TAG],
    ]),
    "mixed/search-policy.txt": ("دستورالعمل جستجوی بایگانی", "", [
        f"{TAG} برای آزمایش مسیر بازبینی، کلید SAND-406 را در دفتر ثبت جستجو کنید. مسئول این مسیر گروه آبی است.",
        f"{TAG} The Blue Team owns the SAND-406 review route.",
    ]),
    "mixed/transfer.jpg": ("کارت تحویل بسته", "", [
        TAG,
        "بستهٔ نمایشی برای واحد بازبینی فرستاده شد.",
        "Package LANTERN-53 goes to the Review Desk.",
    ]),
    "private/reviewer-note.txt": ("یادداشت خصوصی بازبین", "", [
        f"{TAG} شناسهٔ پیگیری خصوصی بازبین CEDAR-819 است.",
        f"{TAG} The reviewer's private tracking code is CEDAR-819.",
    ]),
}


def rtl(text):
    for char in text:
        direction = unicodedata.bidirectional(char)
        if direction in {"R", "AL", "L"}:
            return direction != "L"
    return False


def word_file(path, title, lines):
    doc = Document()
    doc.core_properties.title = title
    doc.core_properties.author = "Document QA demo"
    for border in doc.styles["Title"]._element.xpath(".//w:pBdr"):
        border.getparent().remove(border)
    for index, line in enumerate([title, *lines]):
        p = doc.add_paragraph(style="Title" if index == 0 else "Normal")
        if rtl(line):
            p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            p._p.get_or_add_pPr().append(OxmlElement("w:bidi"))
        p.paragraph_format.space_after = Pt(18)
        run = p.add_run(line)
        run.font.name = "Arial"
        run._element.get_or_add_rPr().rFonts.set(qn("w:cs"), "Arial")
        run.bold = index == 0
        size = 24 if index == 0 else 13
        run.font.size = Pt(size)
        cs_size = OxmlElement("w:szCs")
        cs_size.set(qn("w:val"), str(size * 2))
        run._element.get_or_add_rPr().append(cs_size)
        run.font.color.rgb = RGBColor.from_string("172B2B")
    doc.save(path)


def spreadsheet(path, lang, rows):
    book = Workbook()
    sheet = book.active
    sheet.title = {"fa": "محصولات", "en": "Components", "mixed": "آزمون‌ها"}[lang]
    sheet.sheet_view.rightToLeft = lang != "en"
    sheet.sheet_view.showGridLines = False
    sheet.freeze_panes = "A2"
    for i, row in enumerate(rows, 1):
        sheet.append(row)
        sheet.row_dimensions[i].height = 40
        for cell in sheet[i]:
            cell.font = Font(name="Arial", size=12, bold=i == 1, color="FFFFFF" if i == 1 else "173330")
            cell.fill = PatternFill("solid", fgColor="15544D" if i == 1 else ("E4EFEB" if i % 2 == 0 else "F5F8F7"))
            cell.alignment = Alignment(vertical="center", horizontal="right" if rtl(str(cell.value)) else "left",
                                       readingOrder=2 if rtl(str(cell.value)) else 1, wrap_text=True, indent=1)
    for i, values in enumerate(zip(*rows), 1):
        sheet.column_dimensions[get_column_letter(i)].width = max(20, max(map(len, values)) * 1.3 + 5)
    sheet.auto_filter.ref = sheet.dimensions
    book.save(path)


def typeset(title, lines):
    """MuPDF shapes Arabic-script glyphs. A sans-serif face helps OCR."""
    doc = pymupdf.open()
    page = doc.new_page(width=650, height=390)
    html = []
    for index, line in enumerate([title, *lines]):
        direction = "rtl" if rtl(line) else "ltr"
        tag = "h1" if index == 0 else "p"
        html.append(f'<{tag} dir="{direction}">{escape(line)}</{tag}>')
    font = next((p for p in (
        Path(os.getenv("SAMPLE_FONT", ".")),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("C:/Windows/Fonts/tahoma.ttf"),
    ) if p.is_file()), None)
    css = "body {font-family:Demo,sans-serif;color:#182e2c;} h1 {font-size:26pt;} p {font-size:18pt;}"
    archive = None
    if font:
        css = f"@font-face {{font-family:Demo;src:url('{font.name}');}} " + css
        archive = pymupdf.Archive(str(font.parent))
    space, scale = page.insert_htmlbox((40, 25, 610, 370), "".join(html), css=css, archive=archive)
    if space < 0 or scale < 0.8:
        raise ValueError(f"Page overflow: {title}")
    return doc


def make_pages(path, title, lines):
    if path.name == "shift-handover.pdf":
        pages = [(lines[0], lines[1:2], False), (lines[2], lines[3:], True)]
    else:
        pages = [(title, lines, path.name == "harf-scan.pdf")]
    with pymupdf.open() as output:
        for heading, body, scan in pages:
            with typeset(heading, body) as doc:
                if path.suffix in {".jpg", ".png"}:
                    pix = doc[0].get_pixmap(matrix=pymupdf.Matrix(2, 2))
                    pix.save(path)
                    return
                if scan:
                    pix = doc[0].get_pixmap(matrix=pymupdf.Matrix(2, 2))
                    page = output.new_page(width=650, height=390)
                    page.insert_image(page.rect, stream=pix.tobytes("png"))
                else:
                    output.insert_pdf(doc)
        output.subset_fonts()
        output.save(path, garbage=4, deflate=True)


def main():
    catalog = []
    for name, (title, source, content) in FILES.items():
        path = ROOT / name
        path.parent.mkdir(parents=True, exist_ok=True)
        lang = path.parent.name
        if path.suffix == ".docx":
            word_file(path, title, content)
        elif path.suffix == ".xlsx":
            spreadsheet(path, lang, content)
        elif path.suffix == ".txt":
            path.write_text("\n\n".join([title, *content]) + "\n", encoding="utf-8")
        else:
            make_pages(path, title, content)
        catalog.append({"path": name, "title": title, "owner": "reviewer" if lang == "private" else "demo",
                        "language": "mixed" if lang == "private" else lang, "public_source": source or None})
    (ROOT / "catalog.json").write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Created {len(catalog)} sample files.")


if __name__ == "__main__":
    main()
