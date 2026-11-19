"""Exercise the same permission boundaries used by the UI, API and Django admin."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIClient

from . import services
from .models import Chunk, Conversation, Document, Turn


class AccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.admin = User.objects.create_superuser("alice", "", "local-tests-only")
        cls.other = User.objects.create_user("bob", password="other-tests-only")
        cls.hidden = Document.objects.create(owner=cls.other, title="Private title",
                                             filename="notes.txt", text="Hidden sentence")
        cls.private_chat = Conversation.objects.create(owner=cls.other, title="Private thread")
        cls.secret_turn = Turn.objects.create(conversation=cls.private_chat, question="Private question", answer="Private answer")

    def setUp(self):
        self.api = APIClient()
        self.api.force_authenticate(self.admin)
        self.client.force_login(self.admin)
        self.vector_mock = patch("library.rag.build_chunks", side_effect=lambda parts: [
            dict(position=i, text=p["text"], location=p["location"], vector=[1.0]) for i, p in enumerate(parts)
        ])
        self.vector_mock.start()
        self.addCleanup(self.vector_mock.stop)

    def test_superuser_api_search_objects_and_history_are_private(self):
        self.assertEqual(self.api.get("/api/documents/?search=Hidden").json(), [])
        self.assertEqual(self.api.get("/api/conversations/").json(), [])
        path = f"/api/documents/{self.hidden.pk}/"
        self.assertEqual(self.api.get(path).status_code, 404)
        self.assertEqual(self.api.patch(path, {"text": "change"}, format="json").status_code, 404)
        self.assertEqual(self.api.delete(path).status_code, 404)
        path = f"/api/conversations/{self.private_chat.pk}/"
        self.assertEqual(self.api.get(path).status_code, 404)
        self.assertEqual(self.api.post(path + "ask/", {"question": "secret?"}).status_code, 404)
        self.assertEqual(self.api.delete(path).status_code, 404)

    def test_superuser_admin_queries_foreign_object_and_account_delete(self):
        for model, obj, secret in [("document", self.hidden, "Hidden sentence"),
                                   ("conversation", self.private_chat, "Private thread"),
                                   ("turn", self.secret_turn, "Private answer")]:
            path = f"/admin/library/{model}/"
            self.assertNotContains(self.client.get(path), str(obj))
            self.assertNotContains(self.client.get(f"{path}{obj.pk}/change/", follow=True), secret)
        self.assertEqual(self.client.get(f"/admin/auth/user/{self.other.pk}/delete/").status_code, 403)
        self.assertEqual(self.client.get(f"/admin/auth/user/{self.other.pk}/password/").status_code, 403)

    def test_admin_upload_edit_search_and_invalid_document(self):
        create = "/admin/library/document/add/"
        bad = self.client.post(create, {"upload": SimpleUploadedFile("bad.bin", b"broken")})
        self.assertEqual(bad.status_code, 200)
        self.assertFalse(Document.objects.filter(owner=self.admin).exists())
        result = self.client.post(create, {"title": "", "upload": SimpleUploadedFile("team.txt", b"Initial value")})
        self.assertEqual(result.status_code, 302)
        doc = Document.objects.get(owner=self.admin)
        self.assertEqual(doc.title, "team")
        self.client.post(f"/admin/library/document/{doc.pk}/change/", {"title": "Edited", "text": "Updated content"})
        self.assertEqual(doc.chunks.get().text, "Updated content")
        self.assertContains(self.client.get("/admin/library/document/?q=Updated"), "Edited")

    def test_api_edit_replaces_index_and_delete_cascades(self):
        created = self.api.post("/api/documents/", {"file": SimpleUploadedFile("test.txt", b"Initial text"),
                                                     "owner": self.other.pk}, format="multipart")
        self.assertEqual(created.status_code, 201)
        doc = Document.objects.get(pk=created.json()["id"])
        self.assertEqual(doc.owner_id, self.admin.pk)
        path = f"/api/documents/{doc.pk}/"
        self.assertEqual(self.api.patch(path, {"text": "New evidence"}, format="json").status_code, 200)
        self.assertEqual(doc.chunks.get().text, "New evidence")
        self.assertEqual(self.api.get("/api/documents/?search=Initial").json(), [])
        self.assertEqual(self.api.delete(path).status_code, 204)
        self.assertFalse(Chunk.objects.filter(document_id=doc.pk).exists())

    def test_failed_reindex_keeps_previous_document(self):
        doc = services.create_document(self.admin, "Kept", SimpleUploadedFile("a.txt", b"Original text"))
        with patch("library.rag.build_chunks", side_effect=services.rag.RAGUnavailable("model unavailable")):
            result = self.api.patch(f"/api/documents/{doc.pk}/", {"text": "Replacement"}, format="json")
        self.assertEqual(result.status_code, 503)
        doc.refresh_from_db()
        self.assertEqual(doc.text, "Original text")
        self.assertEqual(doc.chunks.get().text, "Original text")

    def test_empty_library_refuses_even_when_another_user_has_documents(self):
        chat = self.api.post("/api/conversations/", {}, format="json").json()
        url = f"/api/conversations/{chat['id']}/"
        result = self.api.post(url + "ask/", {"question": "What is the secret?"}, format="json")
        self.assertEqual(result.status_code, 201)
        self.assertIn("not find enough", result.json()["answer"])
        self.assertEqual(result.json()["sources"], [])
        self.assertEqual(len(self.api.get(url).json()["turns"]), 1)

    def test_followup_uses_only_history_of_selected_conversation(self):
        first = Conversation.objects.create(owner=self.admin)
        another = Conversation.objects.create(owner=self.admin)
        first.turns.create(question="Which product?", answer="Alefba")
        another.turns.create(question="Unrelated project", answer="Other")
        with patch("library.rag.answer_question", return_value=("Insufficient", [])) as answer:
            services.ask(self.admin, first, "What is its limit?")
        self.assertEqual([t.question for t in answer.call_args.args[1]], ["Which product?"])

    def test_anonymous_denied_and_session_write_needs_csrf(self):
        self.assertEqual(APIClient().get("/api/documents/").status_code, 401)
        browser = APIClient(enforce_csrf_checks=True)
        browser.force_login(self.admin)
        self.assertEqual(browser.post("/api/conversations/", {}, format="json").status_code, 403)
