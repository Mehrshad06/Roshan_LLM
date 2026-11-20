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


def prepare_answer(user, conversation, question, replace_id=None):
    if conversation.owner_id != user.pk:
        raise Conversation.DoesNotExist
    history = list(reversed(list(conversation.turns.order_by("-pk")[:6])))
    latest = history[-1].pk if history else None
    if replace_id is not None and latest != replace_id:
        raise Conflict("فقط آخرین پیام گفت‌وگو قابل ویرایش است.")
    answer, sources = rag.answer_question(user, history[:-1] if replace_id else history, question)
    filenames = dict(Document.objects.filter(owner=user, pk__in=[s["document_id"] for s in sources])
                     .values_list("pk", "filename"))
    sources = [dict(s, filename=filenames.get(s["document_id"], "")) for s in sources]
    return dict(user_id=user.pk, conversation_id=conversation.pk, latest=latest, replace_id=replace_id,
                question=question, answer=answer, sources=sources)


def save_answer(user, conversation, draft):
    if (draft["user_id"], draft["conversation_id"]) != (user.pk, conversation.pk):
        raise Conflict("پاسخ به این گفت‌وگو تعلق ندارد.")
    question, answer, sources = draft["question"], draft["answer"], draft["sources"]
    with transaction.atomic():
        current = Conversation.objects.filter(pk=conversation.pk, owner=user).first()
        if not current or current.turns.order_by("-pk").values_list("pk", flat=True).first() != draft["latest"]:
            raise Conflict("این گفت‌وگو تغییر کرد. آن را باز کنید و پرسش را دوباره بفرستید.")
        for source in sources:
            if not Chunk.objects.filter(document__owner=user, document_id=source["document_id"],
                                        location=source["location"], text__contains=source["quote"]).exists():
                raise Conflict("سند منبع تغییر کرده است. پرسش را دوباره بفرستید.")
        if draft["replace_id"]:
            current.turns.filter(pk=draft["replace_id"]).delete()
        if not current.turns.exists():
            current.title = question[:100]
            current.save(update_fields=["title"])
        return current.turns.create(question=question, answer=answer, sources=sources)


def ask(user, conversation, question):
    return save_answer(user, conversation, prepare_answer(user, conversation, question))
