"""Build an evidence-backed graph from the current owner's indexed passages."""
import re
from collections import Counter
from itertools import combinations
from pathlib import Path

import numpy as np
from django.db.models import Prefetch

from .models import Chunk, Document

CODE = re.compile(r"\b[a-z]{2,}[\-_]\d+[a-z0-9]*\b", re.I)
STOP = set("""this that with from into have were been their each these test data document
documents sample file text using used about which when then after before your result
برای آزمایشی داده این است شود شده باشد های سند فایل متن تواند کند کنید درباره یک""".split())


def terms(text):
    return {w for w in re.findall(r"[^\W\d_]{3,}", text.casefold()) if w not in STOP}


def graph(user):
    docs = list(Document.objects.filter(owner=user).defer("text").order_by("pk").prefetch_related(
        Prefetch("chunks", queryset=Chunk.objects.order_by("position"), to_attr="passages")))
    nodes = [dict(id=d.pk, title=d.title, filename=d.filename) for d in docs]
    frequency = Counter()
    for doc in docs:
        vocabulary = set()
        for p in doc.passages:
            p.words = terms(p.text)
            p.codes = {m.upper() for m in CODE.findall(p.text)}
            p.embedding = np.asarray(p.vector, dtype=np.float32)
            vocabulary.update(p.words)
        frequency.update(vocabulary)

    edges = []
    for left, right in combinations(docs, 2):
        best = None
        for a in left.passages:
            for b in right.passages:
                codes = sorted(a.codes & b.codes)
                shared = sorted((w for w in a.words & b.words if frequency[w] <= max(2, len(docs) // 2)),
                                key=lambda w: (frequency[w], -len(w), w))
                similarity = float(a.embedding @ b.embedding) if a.embedding.size and a.embedding.shape == b.embedding.shape else 0
                if codes:
                    kind, labels, rank = "identifier", codes, 3
                elif len(shared) >= 2 or (shared and similarity >= 0.64):
                    kind, labels, rank = "terms", shared[:3], 2
                elif similarity >= 0.86 and a.words and b.words:
                    kind, labels, rank = "semantic", [], 1
                else:
                    continue
                score = (rank, len(labels), similarity)
                if best is None or score > best[0]:
                    evidence = [dict(document_id=d.pk, title=d.title, location=p.location, quote=p.text)
                                for d, p in ((left, a), (right, b))]
                    best = score, dict(source=left.pk, target=right.pk, kind=kind, terms=labels, evidence=evidence)
        if best:
            edges.append(best)
    return dict(nodes=nodes, edges=[edge for _, edge in sorted(edges, key=lambda item: item[0], reverse=True)])


def relation_answer(user, turns, question, language, anchor_id=None):
    q = question.casefold().replace("\u200c", " ")
    if not (re.search(r"مرتبط|ارتباط|رابطه|شباهت|مشابه|related|relationships?|similar|connected", q)
            and re.search(r"سند|اسناد|فایل|documents?|files?|\.pdf|\.docx|\.xlsx|\.txt", q)):
        return None
    data = graph(user)
    nodes = {node["id"]: node for node in data["nodes"]}
    explicit = [i for i, n in nodes.items() if any(
        re.search(r"(?<!\w)" + re.escape(name.casefold()) + r"(?!\w)", q)
        for name in (n["filename"], n["title"], Path(n["filename"]).stem) if name)]
    ids = {anchor_id} & nodes.keys() if anchor_id else set(explicit)
    if not ids and not re.search(r"\b[\w-]+\.(pdf|docx|xlsx|txt|png|jpe?g)\b", q):
        history = list(turns)
        if history:
            ids = {s.get("document_id") for s in history[-1].sources} & nodes.keys()
    en = language == "en"
    if len(ids) != 1:
        return ("Which document should I start with? Send its filename." if en else
                "می‌خواهی ارتباط کدام سند را بررسی کنم؟ نام فایل را بفرست."), []
    anchor = ids.pop()
    lines, citations = [], []
    for edge in data["edges"]:
        if anchor not in (edge["source"], edge["target"]):
            continue
        other = edge["target"] if anchor == edge["source"] else edge["source"]
        reason = {"identifier": ("shared identifier", "شناسهٔ مشترک"), "terms": ("shared terms", "واژه‌های مشترک"),
                  "semantic": ("possible similarity in meaning", "شباهت احتمالی در معنی دو بخش")}[edge["kind"]][not en]
        label = "، ".join(edge["terms"])
        i = len(citations) + 1
        lines.append(f"• {nodes[other]['filename']} — {reason} {label} [{i}] [{i+1}]")
        citations.extend(edge["evidence"])
    name = nodes[anchor]["filename"]
    if not lines:
        return (f"I found no supported link to {name} in your library." if en else
                f"در اسناد کتابخانه‌ات شاهد کافی برای ارتباط با {name} پیدا نکردم."), []
    heading = f"Documents related to {name}" if en else f"سندهای مرتبط با {name}"
    return "\n".join([heading, *lines]), citations
