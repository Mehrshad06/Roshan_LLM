from pathlib import Path
import re

from django.shortcuts import get_object_or_404

from django.utils.translation import gettext
from django.db import transaction
from langchain_core.runnables import RunnableLambda

from . import extraction, rag
from .models import Chunk, Conversation, Document, Turn


class Conflict(Exception):
    """Another request changed the data while this request was running."""


MAX_TEXT = extraction.MAX_CHARS


def prepare_sections(sections):
    text = "\n\n".join(part["text"] for part in sections).strip()
    if not text or len(text) > MAX_TEXT:
        raise ValueError(gettext("متن سند باید بین ۱ تا ۶۰۰٬۰۰۰ نویسه باشد."))
    return text, rag.build_chunks(sections)


def prepare_upload(upload):
    # The dashboard, admin, API and demo importer use the same ingestion chain.
    chain = RunnableLambda(extraction.extract_sections) | RunnableLambda(prepare_sections)
    return chain.invoke(upload)


def prepare_edit(text):
    return prepare_sections([{"location": "متن ویرایش‌شده", "text": text.strip()}])


def store_document(document, prepared=None, *, is_new=False):
    # Embed first, then commit the document and its index as a single change.
    with transaction.atomic():
        if not is_new:
            current = Document.objects.filter(pk=document.pk, owner=document.owner).first()
            if not current or current.updated_at != document.updated_at:
                raise Conflict(gettext("این سند هم‌زمان تغییر کرده است. دوباره آن را باز کنید."))
        if prepared is not None:
            document.text, chunks = prepared
        document.save(force_insert=is_new)
        if prepared is not None:
            document.chunks.all().delete()
            Chunk.objects.bulk_create([Chunk(document=document, **data) for data in chunks])
    return document


def create_document(owner, title, upload):
    name = Path(upload.name.replace("\\", "/")).name[:255]
    document = Document(owner=owner, title=title.strip() or Path(name).stem[:240], filename=name)
    return store_document(document, prepare_upload(upload), is_new=True)


def project_choices(user, question):
    """Clarify a generic project request when the library has several plausible projects."""
    subject = re.search(r"پروژه|project", question, re.I)
    request = re.search(r"چی می|چه می|چیکار|چه کار|چی کار|خواسته|الزام|requirements?|asks? us|need to do", question, re.I)
    if not subject or not request:
        return []
    docs = user.document_set.order_by("title").values("id", "title", "filename")
    candidates = [d for d in docs if re.search(r"پروژه|تکلیف|پایلوت|project|assignment|pilot|brief",
                                                d["title"] + " " + d["filename"], re.I)]
    if len(candidates) < 2 or re.search(r"\b[a-z]+[-_]\d+\b", question, re.I):
        return []
    for d in candidates:
        if any(name and name.casefold() in question.casefold() for name in (d["title"], Path(d["filename"]).stem)):
            return []
    return candidates[:5]


def prepare_answer(user, conversation, question, replace_id=None, document_id=None):
    if conversation.owner_id != user.pk:
        raise Conversation.DoesNotExist
    history = list(reversed(list(conversation.turns.order_by("-pk")[:6])))
    latest = history[-1].pk if history else None
    if replace_id is not None and latest != replace_id:
        raise Conflict(gettext("فقط آخرین پیام گفت‌وگو قابل ویرایش است."))
    previous = history[:-1] if replace_id else history
    effective_question = question
    if previous and previous[-1].choices and not document_id:
        matches = [d for d in previous[-1].choices if question.strip().casefold() in
                   {d["filename"].casefold(), d["title"].casefold(), Path(d["filename"]).stem.casefold()}]
        if len(matches) == 1:
            document_id = matches[0]["id"]
            effective_question = previous[-1].question
    choices = [] if document_id else project_choices(user, question)
    if choices and previous:
        last_sources = {s.get("document_id") for s in previous[-1].sources}
        if len(last_sources) == 1 and last_sources <= {d["id"] for d in choices}:
            document_id = last_sources.pop()
            choices = []
    if document_id is not None:
        get_object_or_404(Document.objects.only("id"), pk=document_id, owner=user)
        previous = [t for t in previous if t.document_id == document_id or
                    {s.get("document_id") for s in t.sources} == {document_id}]
    if choices:
        prompt = "Which project do you mean?" if rag._default_language(question) == "en" else "منظورت کدام پروژه است؟"
        answer, sources = prompt + " " + " / ".join(d["filename"] for d in choices), []
    else:
        answer, sources = rag.answer_question(user, previous, effective_question, selected=conversation.language_model,
                                              document_id=document_id)
    filenames = dict(Document.objects.filter(owner=user, pk__in=[s["document_id"] for s in sources])
                     .values_list("pk", "filename"))
    sources = [dict(s, filename=filenames.get(s["document_id"], "")) for s in sources]
    return dict(user_id=user.pk, conversation_id=conversation.pk, latest=latest, replace_id=replace_id,
                document_id=document_id, choices=choices, language_model_id=conversation.language_model_id, question=question, answer=answer, sources=sources)


def save_answer(user, conversation, draft):
    if (draft["user_id"], draft["conversation_id"]) != (user.pk, conversation.pk):
        raise Conflict(gettext("پاسخ به این گفت‌وگو تعلق ندارد."))
    question, answer, sources = draft["question"], draft["answer"], draft["sources"]
    with transaction.atomic():
        current = Conversation.objects.filter(pk=conversation.pk, owner=user).first()
        if not current or current.language_model_id != draft.get("language_model_id") or current.turns.order_by("-pk").values_list("pk", flat=True).first() != draft["latest"]:
            raise Conflict(gettext("این گفت‌وگو تغییر کرد. آن را باز کنید و پرسش را دوباره بفرستید."))
        document_id = draft.get("document_id")
        if document_id and not Document.objects.filter(pk=document_id, owner=user).exists():
            raise Conflict(gettext("سند منبع تغییر کرده است. پرسش را دوباره بفرستید."))
        for source in sources:
            if not Chunk.objects.filter(document__owner=user, document_id=source["document_id"],
                                        location=source["location"], text__contains=source["quote"]).exists():
                raise Conflict(gettext("سند منبع تغییر کرده است. پرسش را دوباره بفرستید."))
        if draft["replace_id"]:
            current.turns.filter(pk=draft["replace_id"]).delete()
        if not current.turns.exists():
            current.title = question[:100]
            current.save(update_fields=["title"])
        return current.turns.create(question=question, answer=answer, sources=sources, document_id=document_id, choices=draft.get("choices", []))


def ask(user, conversation, question, document_id=None):
    return save_answer(user, conversation, prepare_answer(user, conversation, question, document_id=document_id))
