"""Load real sample uploads through the same ingestion path as the API."""

import json
import os
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.files import File
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from library.models import Conversation, Document
from library.services import create_document


def seed_example_chat(pilot):
    """A labeled, prewritten tour. Record only excerpts present in the real index."""
    examples = [
        ("پایلوت ALF-27 چه ورودی‌هایی می‌پذیرد؟", "این پایلوت تصویر PNG و JPEG می‌پذیرد.",
         "ورودی PNG و JPEG می‌پذیرد."),
        ("حجم هر فایلش چقدر است؟", "سقف حجم هر فایل در این پایلوت ۲۴ مگابایت است.",
         "سقف حجم هر فایل در این پایلوت ۲۴ مگابایت است."),
    ]
    with transaction.atomic():
        chat = Conversation.objects.create(owner=pilot.owner, title="نمونهٔ آموزشی | پایلوت الفبا")
        for question, answer, quote in examples:
            chunk = pilot.chunks.filter(text__contains=quote).order_by("position").first()
            if not chunk:
                raise CommandError("The pilot fixture no longer contains the expected demo quotation.")
            chat.turns.create(question=question, answer=answer, sources=[{
                "document_id": pilot.pk, "title": pilot.title, "location": chunk.location, "quote": quote,
            }])


class Command(BaseCommand):
    help = "Create two demo accounts and import any missing demo files."

    def add_arguments(self, parser):
        parser.add_argument("--accounts-only", action="store_true",
                            help="Activate sample accounts without restoring deleted documents.")

    def handle(self, *args, **options):
        users = {}
        with transaction.atomic():
            for name in ("demo", "reviewer"):
                user, created = get_user_model().objects.get_or_create(username=name)
                if created or not user.has_usable_password():
                    variable = f"{name.upper()}_PASSWORD"
                    password = os.getenv(variable)
                    if not password:
                        raise CommandError(f"Set {variable} in .env before activating the demo.")
                    user.set_password(password)
                    user.is_staff = name == "demo"
                    user.save()
                users[name] = user
            permissions = Permission.objects.filter(content_type__app_label="library", codename__in=[
                "add_document", "view_document", "change_document", "delete_document",
                "view_conversation", "view_turn", "add_turn",
                "view_languagemodel", "add_languagemodel", "change_languagemodel", "delete_languagemodel",
            ])
            users["demo"].user_permissions.add(*permissions)
        if options["accounts_only"]:
            self.stdout.write("Demo accounts are ready.")
            return
        root = Path(settings.BASE_DIR) / "samples"
        catalog = json.loads((root / "catalog.json").read_text(encoding="utf-8"))
        count = 0
        for item in catalog:
            user = users[item["owner"]]
            path = root / item["path"]
            if Document.objects.filter(owner=user, filename=path.name).exists():
                continue
            with path.open("rb") as raw, transaction.atomic():
                document = create_document(user, item["title"], File(raw, name=path.name))
                if path.name == "alefba-pilot.docx" and not user.conversation_set.exists():
                    seed_example_chat(document)
            count += 1
            self.stdout.write(f"Imported {path.name} for {user.username}.")
        self.stdout.write(self.style.SUCCESS(f"Imported {count} new documents."))
