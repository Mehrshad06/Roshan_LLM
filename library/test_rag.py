import json
import os
from unittest.mock import patch

import numpy as np
from django.contrib.auth import get_user_model
from django.test import TestCase
from langchain_core.runnables import RunnableLambda

from . import rag
from .models import Chunk, Conversation, Document


class RetrievalTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser("alice", password="unused")
        other = get_user_model().objects.create_user("bob")
        self.owned = Document.objects.create(owner=self.user, title="Alfba manual")
        self.other = Document.objects.create(owner=other, title="Another customer's manual")
        self.conversation = Conversation.objects.create(owner=self.user)

    def add_chunk(self, document, text, position=0, vector=(1, 0)):
        return Chunk.objects.create(document=document, position=position, text=text,
                                    location=f"Page {position + 1}", vector=list(vector))

    def test_superuser_with_empty_library_abstains_in_requested_language(self):
        self.add_chunk(self.other, "PRIVATE-DOC-1 handles 81 MB.")
        with patch("library.rag.ChatOpenAI", side_effect=AssertionError("unexpected LLM call")):
            text, sources = rag.answer_question(self.user, [], "حداکثر حجم چیست؟ به انگلیسی جواب بده")
        self.assertEqual((text, sources), (rag.ABSTAIN["en"], []))

    def test_greeting_with_an_empty_library(self):
        answer, sources = rag.answer_question(self.user, [], "سلام!")
        self.assertTrue(answer.startswith("سلام"))
        self.assertEqual(sources, [])

    def test_overview_uses_different_owned_documents(self):
        self.add_chunk(self.owned, "Pilot instructions")
        second = Document.objects.create(owner=self.user, title="گزارش")
        self.add_chunk(second, "Archive handover")
        self.add_chunk(self.other, "Private note")
        with patch.object(rag, "_invoke", side_effect=AssertionError("unneeded model call")):
            _, excerpts = rag.answer_question(self.user, [], "این ها اسناد چه چیز هایی هست ؟")
        self.assertEqual({entry["title"] for entry in excerpts}, {self.owned.title, second.title})

    def test_social_question_from_history_and_greeting_with_document_request(self):
        self.add_chunk(self.owned, "The deadline is Friday.")
        with patch.object(rag, "_invoke") as invoke:
            answer, sources = rag.answer_question(self.user, [], "سلام چطوری ؟")
            self.assertIn("سلام", answer)
            self.assertFalse(sources)
            invoke.assert_not_called()
            invoke.side_effect = rag.RAGUnavailable("planner called")
            with self.assertRaisesRegex(rag.RAGUnavailable, "planner called"):
                rag.answer_question(self.user, [], "سلام، استاد چه مهلتی داده؟")

    def test_second_pass_reads_new_evidence(self):
        first = self.add_chunk(self.owned, "Orientation.")
        second = self.add_chunk(self.owned, "The deadline is Friday.", position=4)
        plan = rag.SearchPlan(standalone="Deadline?", alternative="Due date?", language="en")
        with (patch.object(rag, "_retrieve", side_effect=[[first], [second]]) as retrieve,
              patch.object(rag, "_invoke", side_effect=[plan, (rag.ABSTAIN["en"], []),
                           ("Friday. [1]", [{"quote": second.text}])])):
            answer, _ = rag.answer_question(self.user, [], "When is it due?")
        self.assertIn("Friday", answer)
        self.assertEqual(retrieve.call_args.args[0], [second])

    def test_help_and_clock_do_not_search_documents(self):
        self.add_chunk(self.owned, "A list of project requirements.")
        with patch.object(rag, "_invoke", side_effect=AssertionError("unexpected model call")):
            for question, expected in [("what are you doing", "search"), ("what time is it?", "clock")]:
                answer, sources = rag.answer_question(self.user, [], question)
                self.assertIn(expected, answer)
                self.assertEqual(sources, [])

    def test_full_library_language_count_without_provider(self):
        self.add_chunk(self.owned, "این سند فارسی است.")
        self.add_chunk(self.owned, "This page is in English.", position=5)
        self.add_chunk(Document.objects.create(owner=self.user, title="English"), "A short guide.")
        self.add_chunk(self.other, "Hidden content.")
        with patch.object(rag, "_invoke", side_effect=AssertionError("provider call")):
            answer, sources = rag.answer_question(self.user, [], "چند تا از این سند ها فقط انگلیسی هست و کدام هم فارسی داره؟")
        self.assertIn("متن 2 سند", answer)
        self.assertIn("انگلیسی (1) — English", answer)
        self.assertIn("فارسی و انگلیسی (1)", answer)
        self.assertEqual({s["location"] for s in sources}, {"Page 1", "Page 6"})
        self.assertNotIn(self.other.pk, [s["document_id"] for s in sources])

    def test_rate_limit_tries_backup_once_then_reports_capacity(self):
        from django.core.cache import cache
        self.addCleanup(cache.clear)
        class Busy(Exception):
            status_code = 429
        def reject(prompt):
            raise Busy()
        with (patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}),
              patch.object(rag, "ChatOpenAI", return_value=RunnableLambda(reject)) as model,
              self.assertRaisesRegex(rag.RAGUnavailable, "ظرفیت")):
            rag._invoke(rag.PLAN, {}, rag.SearchPlan)
        self.assertEqual(model.call_count, 2)

    def test_followup_is_retrieved_again_and_only_current_evidence_can_be_cited(self):
        private = self.add_chunk(self.other, "PRIVATE-DOC-1 handles 81 MB.")
        first = self.add_chunk(self.owned, "Alfba handles scanned documents.")
        limit = self.add_chunk(self.owned, "The Alfba upload limit is 24 MB.", position=1)
        previous = self.conversation.turns.create(question="الفبا چیست؟", answer="سامانهٔ بازشناسی متن.")
        payloads = []

        def reply(prompt):
            payload = json.loads(prompt.to_messages()[-1].content)
            payloads.append(payload)
            if "history" in payload:
                return json.dumps({"standalone": "What is the Alfba upload limit?",
                                   "alternative": "سقف حجم الفبا چقدر است؟", "language": "fa"})
            number = next(row["source"] for row in payload["excerpts"] if row["text"] == limit.text)
            return json.dumps({"claims": [{"sentence": "The limit is 24 MB.",
                                           "source": number, "quote": limit.text}]})

        with (patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}),
              patch("library.rag.ChatOpenAI", return_value=RunnableLambda(reply)),
              patch("library.rag._vectors", side_effect=lambda qs: np.tile([1, 0], (len(qs), 1)))):
            answer, sources = rag.answer_question(
                self.user, [previous], "حجمش چقدر است؟ به انگلیسی جواب بده"
            )
        self.assertEqual(answer, "The limit is 24 MB. [1]")
        self.assertEqual(sources, [{"document_id": self.owned.pk, "title": self.owned.title,
                                    "location": limit.location, "quote": limit.text}])
        self.assertEqual(payloads[0]["history"][0]["question"], previous.question)
        self.assertEqual(payloads[1]["answer_language"], "en")
        self.assertIn(first.text, [row["text"] for row in payloads[1]["excerpts"]])
        self.assertNotIn(private.text, str(payloads))

    def test_fabricated_quote_rejected_and_fallback_model_can_abstain(self):
        chunk = self.add_chunk(self.owned, "The Alfba upload limit is 24 MB.")
        invented = {"claims": [{"sentence": "The limit is 50 MB.", "source": 1, "quote": "50 MB"}]}
        primary = RunnableLambda(lambda prompt: json.dumps(invented))
        fallback = RunnableLambda(lambda prompt: '{"claims":[]}')
        with (patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}),
              patch("library.rag.ChatOpenAI", side_effect=[primary, fallback])):
            checked = rag._invoke(rag.GROUND, {}, rag.Answer,
                                  validate=lambda result: rag._checked_answer(result, [chunk], "fa"))
        self.assertEqual(checked, (rag.ABSTAIN["fa"], []))

    def test_exact_lexical_hit_with_persian_digits_and_adjacent_context(self):
        relevant = self.add_chunk(self.owned, "Sample code AB-412.", vector=(0, 1))
        neighbor = self.add_chunk(self.owned, "This row explains the units.", 1, vector=(0, 1))
        unrelated = self.add_chunk(self.owned, "Unrelated.", 4, vector=(0, 1))
        with patch("library.rag._vectors", return_value=np.array([[1, 0]])):
            result = rag._retrieve([unrelated, neighbor, relevant], ["AB-۴۱۲"])
        self.assertEqual(result, [relevant, neighbor])

    def test_exact_code_outranks_semantic_distractors_in_search_api(self):
        self.add_chunk(self.other, "AB-412 private")
        for pos in range(6):
            self.add_chunk(self.owned, "Pilot handbook AB-410", pos)
        hit = self.add_chunk(self.owned, "Pilot handbook AB-412", 8, vector=(0, 1))
        self.client.force_login(self.user)
        with patch.object(rag, "_vectors", return_value=np.array([[1, 0]])):
            rows = self.client.get("/api/documents/search/", {"q": "Pilot AB-۴۱۲"}).json()
        self.assertEqual(rows[0]["quote"], hit.text)
        self.assertTrue(all(row["document_id"] == self.owned.pk for row in rows))
        self.assertEqual(self.client.get("/api/documents/search/").status_code, 400)
        self.assertContains(self.client.get("/api/docs/"), "SwaggerUIBundle")
        self.assertContains(self.client.get("/api/schema/?format=json"), "/api/documents/search/")

    def test_existing_quote_cannot_support_a_different_numeric_limit(self):
        chunk = self.add_chunk(self.owned, "سقف بارگذاری ۲۴ مگابایت است.")
        result = rag.Answer(claims=[rag.Claim(
            sentence="The upload limit is 42 MB.", source=1, quote=chunk.text
        )])
        with self.assertRaises(ValueError):
            rag._checked_answer(result, [chunk], "en")

    def test_missing_key_reports_service_failure(self):
        self.add_chunk(self.owned, "Sample")
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": ""}), self.assertRaises(rag.RAGUnavailable):
            rag.answer_question(self.user, [], "What is the limit?")
