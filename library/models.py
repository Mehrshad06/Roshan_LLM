from django.utils.translation import gettext_lazy as gettext
from django.conf import settings
from django.db import models


class Document(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    title = models.CharField(gettext("عنوان"), max_length=240)
    filename = models.CharField(gettext("نام فایل"), max_length=255)
    text = models.TextField(gettext("متن کامل"))
    created_at = models.DateTimeField(gettext("زمان ایجاد"), auto_now_add=True)
    updated_at = models.DateTimeField(gettext("آخرین تغییر"), auto_now=True)

    class Meta:
        ordering = ["-updated_at", "-id"]
        verbose_name = gettext("سند")
        verbose_name_plural = gettext("اسناد")

    def __str__(self):
        return self.title


class Chunk(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="chunks")
    position = models.PositiveIntegerField()
    location = models.CharField(max_length=255)
    text = models.TextField()
    vector = models.JSONField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["document", "position"], name="unique_chunk_position")]


class Conversation(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    title = models.CharField(gettext("عنوان"), max_length=160, default="گفت‌وگوی جدید")
    created_at = models.DateTimeField(gettext("زمان ایجاد"), auto_now_add=True)

    class Meta:
        ordering = ["-id"]
        verbose_name = gettext("گفت‌وگو")
        verbose_name_plural = gettext("گفت‌وگوها")

    def __str__(self):
        return self.title


class Turn(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="turns")
    question = models.TextField(gettext("پرسش"))
    answer = models.TextField(gettext("پاسخ"))
    sources = models.JSONField(gettext("شواهد"), default=list)
    created_at = models.DateTimeField(gettext("زمان ایجاد"), auto_now_add=True)

    class Meta:
        ordering = ["id"]
        verbose_name = gettext("پرسش و پاسخ")
        verbose_name_plural = gettext("پرسش‌ها و پاسخ‌ها")

    def __str__(self):
        return self.question[:80]
