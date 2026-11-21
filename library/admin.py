from pathlib import Path

from django.utils.translation import gettext_lazy as gettext
from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import Group, User
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import reverse

from . import services
from .models import Conversation, Document, LanguageModel, Turn
from .rag import RAGUnavailable

admin.site.site_header = gettext("روشن | مدیریت کتابخانه")
admin.site.site_title = gettext("مدیریت روشن")
admin.site.index_title = gettext("مدیریت حساب و اسناد")


class OwnedAdmin(admin.ModelAdmin):
    def get_queryset(self, request):
        return super().get_queryset(request).filter(owner=request.user)


class DocumentForm(forms.ModelForm):
    upload = forms.FileField(label=gettext("فایل سند"), required=False)
    title = forms.CharField(label=gettext("عنوان"), max_length=240, required=False)

    class Meta:
        model = Document
        fields = ["title", "text"]

    def clean(self):
        data = super().clean()
        self.prepared = None
        if self.errors:
            return data
        upload = data.get("upload")
        try:
            if not self.instance.pk:
                if not upload:
                    raise forms.ValidationError(gettext("فایل سند را انتخاب کنید."))
                self.prepared = services.prepare_upload(upload)
                data["title"] = data.get("title") or Path(upload.name).stem[:240]
                self.instance.filename = Path(upload.name).name[:255]
            elif not data.get("title"):
                self.add_error("title", gettext("عنوان سند را وارد کنید."))
            elif "text" in self.changed_data:
                self.prepared = services.prepare_edit(data["text"])
        except (ValueError, RAGUnavailable) as exc:
            raise forms.ValidationError(str(exc)) from exc
        return data


@admin.register(Document)
class DocumentAdmin(OwnedAdmin):
    form = DocumentForm
    list_display = ["title", "filename", "updated_at"]
    search_fields = ["title", "text", "filename"]
    readonly_fields = ["filename", "created_at", "updated_at"]

    def get_fields(self, request, obj=None):
        return ["title", "filename", "text", "created_at", "updated_at"] if obj else ["title", "upload"]

    def save_model(self, request, obj, form, change):
        obj.owner = request.user
        services.store_document(obj, form.prepared, is_new=not change)


@admin.register(LanguageModel)
class LanguageModelAdmin(admin.ModelAdmin):
    list_display = ["name", "provider", "model_id", "priority"]
    list_filter = ["provider"]


@admin.register(Conversation)
class ConversationAdmin(OwnedAdmin):
    fields = ["title", "language_model"]
    list_display = ["title", "created_at"]

    def save_model(self, request, obj, form, change):
        obj.owner = request.user
        super().save_model(request, obj, form, change)


class QuestionForm(forms.Form):
    conversation = forms.ModelChoiceField(label=gettext("گفت‌وگو"), queryset=Conversation.objects.none(),
                                          required=False, empty_label=gettext("شروع گفت‌وگوی جدید"))
    question = forms.CharField(label=gettext("پرسش"), max_length=3000, widget=forms.Textarea(attrs={"rows": 3}))


@admin.register(Turn)
class TurnAdmin(admin.ModelAdmin):
    list_display = ["__str__", "conversation", "created_at"]
    search_fields = ["question", "answer"]
    readonly_fields = ["conversation", "question", "answer", "evidence", "created_at"]
    fields = readonly_fields

    @admin.display(description=gettext("شواهد پاسخ"))
    def evidence(self, obj):
        return "\n\n".join(f'{s["title"]} · {s["location"]}\n{s["quote"]}' for s in obj.sources) or "—"

    def get_queryset(self, request):
        return super().get_queryset(request).filter(conversation__owner=request.user).select_related("conversation")

    def has_change_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request):
        return request.user.has_perm("library.add_turn")

    def add_view(self, request, form_url="", extra_context=None):
        if not self.has_add_permission(request):
            raise PermissionDenied
        form = QuestionForm(request.POST or None)
        form.fields["conversation"].queryset = Conversation.objects.filter(owner=request.user)
        if form.is_valid():
            conversation = form.cleaned_data["conversation"]
            new_conversation = conversation is None
            if new_conversation:
                conversation = Conversation.objects.create(owner=request.user)
            try:
                turn = services.ask(request.user, conversation, form.cleaned_data["question"])
            except (RAGUnavailable, services.Conflict) as exc:
                if new_conversation and not conversation.turns.exists():
                    conversation.delete()
                form.add_error(None, str(exc))
            else:
                return HttpResponseRedirect(reverse("admin:library_turn_change", args=[turn.pk]))
        return TemplateResponse(request, "admin/question.html", {
            **admin.site.each_context(request), "opts": self.model._meta,
            "title": gettext("پرسش از اسناد من"), "form": form,
        })


admin.site.unregister(Group)
admin.site.unregister(User)


@admin.register(User)
class AccountAdmin(UserAdmin):
    # Account maintenance never expands document querysets. Deactivation preserves history.
    fieldsets = [
        (None, {"fields": ["username", "first_name", "last_name", "email"]}),
        (gettext("دسترسی"), {"fields": ["is_active", "is_staff", "user_permissions"]}),
    ]
    list_display = ["username", "is_staff", "is_active"]
    list_filter = ["is_active", "is_staff"]
    filter_horizontal = ["user_permissions"]

    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    has_change_permission = has_add_permission = has_view_permission

    def has_delete_permission(self, request, obj=None):
        return False

    def user_change_password(self, request, id, form_url=""):
        if str(request.user.pk) != str(id):
            raise PermissionDenied
        return super().user_change_password(request, id, form_url)
