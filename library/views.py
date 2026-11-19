from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from . import services
from .models import Conversation, Document
from .rag import RAGUnavailable
from .serializers import (ConversationDetail, ConversationSummary, DocumentDetail,
                          DocumentSummary, EditInput, QuestionInput, TurnOutput, UploadInput)


@login_required
@ensure_csrf_cookie
def dashboard(request):
    return render(request, "dashboard.html")


class ScopedViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    def handle_exception(self, exc):
        if isinstance(exc, (ValueError, RAGUnavailable, services.Conflict)):
            status = 503 if isinstance(exc, RAGUnavailable) else 409 if isinstance(exc, services.Conflict) else 400
            return Response({"detail": str(exc)}, status=status)
        return super().handle_exception(exc)


class DocumentViewSet(mixins.DestroyModelMixin, ScopedViewSet):
    def get_queryset(self):
        docs = Document.objects.filter(owner=self.request.user)
        term = self.request.query_params.get("search", "").strip()
        if self.action == "list":
            docs = docs.defer("text")
            if term:
                docs = docs.filter(Q(title__icontains=term) | Q(text__icontains=term) | Q(filename__icontains=term))
        return docs

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


class ConversationViewSet(mixins.DestroyModelMixin, ScopedViewSet):
    def get_queryset(self):
        return Conversation.objects.filter(owner=self.request.user)

    def get_serializer_class(self):
        return ConversationDetail if self.action == "retrieve" else ConversationSummary

    def create(self, request):
        conversation = Conversation.objects.create(owner=request.user)
        return Response(ConversationSummary(conversation).data, status=201)

    @action(detail=True, methods=["post"])
    def ask(self, request, pk=None):
        conversation = self.get_object()
        form = QuestionInput(data=request.data)
        form.is_valid(raise_exception=True)
        turn = services.ask(request.user, conversation, form.validated_data["question"])
        return Response(TurnOutput(turn).data, status=201)
