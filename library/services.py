from pathlib import Path

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
        raise ValueError("متن سند باید بین ۱ تا ۶۰۰٬۰۰۰ نویسه باشد.")
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
                raise Conflict("این سند هم‌زمان تغییر کرده است. دوباره آن را باز کنید.")
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


def ask(user, conversation, question):
    if conversation.owner_id != user.pk:
        raise Conversation.DoesNotExist
    history = list(reversed(list(conversation.turns.order_by("-pk")[:6])))
    answer, sources = rag.answer_question(user, history, question)
    with transaction.atomic():
        current = Conversation.objects.filter(pk=conversation.pk, owner=user).first()
        if not current or current.turns.order_by("-pk").values_list("pk", flat=True).first() != (
            history[-1].pk if history else None
        ):
            raise Conflict("این گفت‌وگو تغییر کرد. آن را باز کنید و پرسش را دوباره بفرستید.")
        for source in sources:
            if not Chunk.objects.filter(document__owner=user, document_id=source["document_id"],
                                        location=source["location"], text__contains=source["quote"]).exists():
                raise Conflict("سند منبع تغییر کرده است. پرسش را دوباره بفرستید.")
        if not history:
            current.title = question[:100]
            current.save(update_fields=["title"])
        return current.turns.create(question=question, answer=answer, sources=sources)
