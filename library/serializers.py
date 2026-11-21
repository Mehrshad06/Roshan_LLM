from django.utils.translation import gettext
from rest_framework import serializers

from .models import Conversation, Document, LanguageModel, Turn
from .services import MAX_TEXT


class DocumentSummary(serializers.ModelSerializer):
    class Meta:
        model = Document
        fields = ["id", "title", "filename", "created_at", "updated_at"]


class DocumentDetail(DocumentSummary):
    class Meta(DocumentSummary.Meta):
        fields = [*DocumentSummary.Meta.fields, "text"]


class UploadInput(serializers.Serializer):
    file = serializers.FileField(max_length=255)
    title = serializers.CharField(max_length=240, allow_blank=True, default="")


class EditInput(serializers.Serializer):
    title = serializers.CharField(max_length=240, required=False)
    text = serializers.CharField(max_length=MAX_TEXT, required=False)

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError(gettext("عنوان یا متن سند را وارد کنید."))
        return attrs


class TurnOutput(serializers.ModelSerializer):
    class Meta:
        model = Turn
        fields = ["id", "question", "answer", "sources", "created_at"]


class ModelOption(serializers.ModelSerializer):
    class Meta:
        model = LanguageModel
        fields = ["id", "name", "provider", "model_id"]


class ModelChoice(serializers.Serializer):
    language_model = serializers.PrimaryKeyRelatedField(queryset=LanguageModel.objects.all(), allow_null=True)


class ConversationSummary(serializers.ModelSerializer):
    class Meta:
        model = Conversation
        fields = ["id", "title", "created_at", "language_model"]


class ConversationDetail(ConversationSummary):
    turns = TurnOutput(many=True, read_only=True)

    class Meta(ConversationSummary.Meta):
        fields = [*ConversationSummary.Meta.fields, "turns"]


class QuestionInput(serializers.Serializer):
    question = serializers.CharField(max_length=3000)


class PreviewInput(QuestionInput):
    replace_id = serializers.IntegerField(min_value=1, allow_null=True, required=False)


class Ticket(serializers.Serializer):
    ticket = serializers.CharField()


class Evidence(serializers.Serializer):
    document_id = serializers.IntegerField()
    title = serializers.CharField()
    location = serializers.CharField()
    quote = serializers.CharField()
