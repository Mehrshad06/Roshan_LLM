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


class LanguageModel(models.Model):
    name = models.CharField(gettext("نام مدل"), max_length=100)
    provider = models.CharField(gettext("ارائه‌دهنده"), max_length=12,
                                choices=[("openrouter", "OpenRouter"), ("ollama", "Ollama")])
    model_id = models.CharField(gettext("شناسهٔ مدل"), max_length=160)
    priority = models.PositiveSmallIntegerField(gettext("اولویت"), default=10)

    class Meta:
        ordering = ["priority", "pk"]
        verbose_name = gettext("مدل زبانی")
        verbose_name_plural = gettext("مدل‌های زبانی")
        constraints = [models.UniqueConstraint(fields=["provider", "model_id"], name="unique_provider_model")]

    def clean(self):
        from django.core.exceptions import ValidationError
        import re
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_./:-]*", self.model_id or ""):
            raise ValidationError({"model_id": gettext("شناسهٔ مدل نامعتبر است.")})
        if self.provider == "openrouter" and not (self.model_id.endswith(":free") or self.model_id == "openrouter/free"):
            raise ValidationError({"model_id": gettext("یک مدل رایگان OpenRouter انتخاب کنید.")})
        if self.provider == "ollama" and self.model_id.endswith((":cloud", "-cloud")):
            raise ValidationError({"model_id": gettext("یک مدل محلی Ollama انتخاب کنید.")})

    def __str__(self):
        return self.name


class Conversation(models.Model):
    language_model = models.ForeignKey(LanguageModel, null=True, blank=True, on_delete=models.SET_NULL,
                                       verbose_name=gettext("مدل زبانی"))
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
