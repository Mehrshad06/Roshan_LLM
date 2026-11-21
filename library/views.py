from django.utils.translation import gettext
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.db.models import Q
from django.shortcuts import get_object_or_404, render
from django.utils.crypto import salted_hmac
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view

from .relations import graph
from .serializers import AnswerRating, DocumentGraph
from . import services
from .models import Conversation, Document, LanguageModel
from .rag import RAGUnavailable, search_evidence
from .serializers import (ModelChoice, ModelOption, Evidence, PreviewInput, Ticket, ConversationDetail, ConversationSummary, DocumentDetail,
                          DocumentSummary, EditInput, QuestionInput, TurnOutput, UploadInput)


@login_required
@ensure_csrf_cookie
def dashboard(request):
    # A stable, non-secret browser storage namespace for this login only.
    chat_session = salted_hmac("workspace-chat", request.session.session_key).hexdigest()
    return render(request, "dashboard.html", {"language_models": LanguageModel.objects.all(),
                                              "documents": request.user.document_set.only("filename").order_by("filename", "pk"),
                                              "chat_session": chat_session})


class ScopedViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    def handle_exception(self, exc):
        if isinstance(exc, (ValueError, RAGUnavailable, services.Conflict)):
            status = 503 if isinstance(exc, RAGUnavailable) else 409 if isinstance(exc, services.Conflict) else 400
            return Response({"detail": str(exc)}, status=status)
        return super().handle_exception(exc)


@extend_schema_view(
    list=extend_schema(parameters=[OpenApiParameter("search", str)]),
    create=extend_schema(request={"multipart/form-data": UploadInput}, responses={201: DocumentDetail}),
    partial_update=extend_schema(request=EditInput, responses=DocumentDetail),
)
@extend_schema(tags=["documents"])
class DocumentViewSet(mixins.DestroyModelMixin, ScopedViewSet):
    queryset = Document.objects.none()

    @extend_schema(responses=DocumentGraph, summary="Document relationships with supporting passages")
    @action(detail=False, methods=["get"], url_path="graph")
    def graph(self, request):
        return Response(graph(request.user))

    @extend_schema(parameters=[OpenApiParameter("q", str, required=True)], responses=Evidence(many=True))
    @action(detail=False, methods=["get"], url_path="search")
    def search(self, request):
        query = request.query_params.get("q", "").strip()
        if not 1 <= len(query) <= 3000:
            raise ValueError(gettext("عبارت جست‌وجو باید بین ۱ تا ۳۰۰۰ نویسه باشد."))
        return Response(search_evidence(request.user, query))

    def get_queryset(self):
        docs = Document.objects.filter(owner=self.request.user)
        term = self.request.query_params.get("search", "").strip()
        if self.action == "list":
            docs = docs.defer("text")
            if term:
                docs = docs.filter(Q(title__icontains=term) | Q(text__icontains=term) | Q(filename__icontains=term))
        return docs

    @extend_schema(parameters=[OpenApiParameter("location", str, description="Include current passages from this cited section.")])
    def retrieve(self, request, pk=None):
        doc = self.get_object()
        location = request.query_params.get("location")
        if location:
            doc.passages = list(doc.chunks.filter(location=location).order_by("position").values_list("text", flat=True))
        return Response(DocumentDetail(doc).data)

    def get_serializer_class(self):
        return DocumentSummary if self.action == "list" else DocumentDetail

    def create(self, request):
        form = UploadInput(data=request.data)
        form.is_valid(raise_exception=True)
        doc = services.create_document(request.user, form.validated_data["title"], form.validated_data["file"])
        return Response(DocumentDetail(doc).data, status=201)

    def partial_update(self, request, pk=None):
        doc = self.get_object()
        form = EditInput(data=request.data)
        form.is_valid(raise_exception=True)
        updates = form.validated_data
        doc.title = updates.get("title", doc.title)
        prepared = services.prepare_edit(updates["text"]) if "text" in updates and updates["text"] != doc.text else None
        return Response(DocumentDetail(services.store_document(doc, prepared)).data)


class LanguageModelViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    queryset = LanguageModel.objects.all()
    serializer_class = ModelOption


@extend_schema_view(create=extend_schema(request=ModelChoice, responses={201: ConversationSummary}))
@extend_schema(tags=["conversations"])
class ConversationViewSet(mixins.DestroyModelMixin, ScopedViewSet):
    queryset = Conversation.objects.none()

    @extend_schema(request=AnswerRating, responses=AnswerRating)
    @action(detail=True, methods=["put"], url_path=r"turns/(?P<turn_id>[0-9]+)/rating")
    def rate(self, request, pk=None, turn_id=None):
        turn = get_object_or_404(self.get_object().turns, pk=turn_id)
        form = AnswerRating(data=request.data)
        form.is_valid(raise_exception=True)
        turn.rating = form.validated_data["rating"]
        turn.save(update_fields=["rating"])
        return Response({"rating": turn.rating})

    @extend_schema(request=PreviewInput, responses=Ticket)
    @action(detail=True, methods=["post"])
    def preview(self, request, pk=None):
        conversation = self.get_object()
        form = PreviewInput(data=request.data)
        form.is_valid(raise_exception=True)
        draft = services.prepare_answer(request.user, conversation, form.validated_data["question"],
                                        form.validated_data.get("replace_id"), form.validated_data.get("document"))
        return Response({"ticket": signing.dumps(draft, salt="chat-preview", compress=True)})

    @extend_schema(request=Ticket, responses={201: TurnOutput})
    @action(detail=True, methods=["post"])
    def confirm(self, request, pk=None):
        conversation = self.get_object()
        try:
            draft = signing.loads(str(request.data.get("ticket", "")), salt="chat-preview", max_age=600)
        except signing.BadSignature as exc:
            raise ValueError(gettext("این پاسخ منقضی یا نامعتبر است. پرسش را دوباره بفرستید.")) from exc
        return Response(TurnOutput(services.save_answer(request.user, conversation, draft)).data, status=201)

    def get_queryset(self):
        return Conversation.objects.filter(owner=self.request.user)

    def get_serializer_class(self):
        return ConversationDetail if self.action == "retrieve" else ConversationSummary

    def create(self, request):
        form = ModelChoice(data=request.data, partial=True)
        form.is_valid(raise_exception=True)
        conversation = Conversation.objects.create(owner=request.user, **form.validated_data)
        return Response(ConversationSummary(conversation).data, status=201)

    @extend_schema(request=ModelChoice, responses=ConversationSummary)
    def partial_update(self, request, pk=None):
        conversation = self.get_object()
        form = ModelChoice(data=request.data)
        form.is_valid(raise_exception=True)
        conversation.language_model = form.validated_data["language_model"]
        conversation.save(update_fields=["language_model"])
        return Response(ConversationSummary(conversation).data)

    @extend_schema(request=QuestionInput, responses={201: TurnOutput})
    @action(detail=True, methods=["post"])
    def ask(self, request, pk=None):
        conversation = self.get_object()
        form = QuestionInput(data=request.data)
        form.is_valid(raise_exception=True)
        turn = services.ask(request.user, conversation, form.validated_data["question"], form.validated_data.get("document"))
        return Response(TurnOutput(turn).data, status=201)
