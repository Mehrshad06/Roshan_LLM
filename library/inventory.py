"""Library-wide Persian/English inventory using the indexed text of each owned file."""
import re
from collections import defaultdict
from itertools import groupby

from .models import Chunk


def asks_for_languages(query):
    language = re.search(r"فارسی|انگلیسی|دوزبانه|دو زبانه|به چه زبان|زبان اسناد|english|persian|bilingual|languages?", query)
    inventory = re.search(r"چند|کدام|کدوم|چه تعداد|شمارش|تفکیک|دسته بندی|how many|which|count|breakdown|list", query)
    content = re.search(r"ترجمه|پشتیبانی|یادگیری|آموزش|translate|support|teach", query)
    return bool(language and inventory and not content)


def language_inventory(user, language):
    fa = language == "fa"
    groups = defaultdict(list)
    sources = []
    rows = (Chunk.objects.filter(document__owner=user).select_related("document")
            .only("document__title", "text", "location", "position")
            .order_by("document_id", "position").iterator())
    for _, passages in groupby(rows, key=lambda c: c.document_id):
        best = {}
        for chunk in passages:
            for line in chunk.text.splitlines():
                clean = re.sub(r"https?://\S+|\b[A-Z]+[-_]?\d+\b", "", line)
                counts = {"fa": len(re.findall(r"[آ-ی]{2,}", clean)),
                          "en": len(re.findall(r"\b[A-Za-z]{2,}\b", clean))}
                for key, count in counts.items():
                    other = counts["en" if key == "fa" else "fa"]
                    if count and (not other or count >= 3) and count > best.get(key, (0,))[0]:
                        best[key] = (count, chunk, line[:300])
        if len(best) == 2:
            # A product name or an OCR fragment on its own line is weak
            # evidence of a second language in an otherwise continuous text.
            best = {key: sample for key, sample in best.items() if sample[0] >= 2}
        category = "mixed" if len(best) == 2 else next(iter(best), "unknown")
        refs = []
        for _, passage, quote in best.values():
            item = dict(document_id=passage.document_id, title=passage.document.title,
                        location=passage.location, quote=quote)
            if not refs or sources[-1] != item:
                sources.append(item)
                refs.append(f"[{len(sources)}]")
        groups[category].append(f"{chunk.document.title} {' '.join(refs)}".strip())
    labels = (["فارسی", "انگلیسی", "فارسی و انگلیسی", "نامشخص"] if fa else
              ["Persian", "English", "Persian and English", "Undetermined"])
    total = sum(map(len, groups.values()))
    lines = [f"متن {total} سند را بررسی کردم." if fa else f"I checked the text of {total} documents."]
    for key, label in zip(("fa", "en", "mixed", "unknown"), labels):
        names = groups[key]
        if names or key != "unknown":
            lines.append(f"{label} ({len(names)})" + (" — " + "، ".join(names) if names else ""))
    return "\n".join(lines), sources
