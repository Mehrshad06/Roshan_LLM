"""Check observable answers and citations against a disposable copy of the shipped demo."""
import os
from pathlib import Path
import shutil
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def evaluate():
    from django.contrib.auth import get_user_model
    from library.models import Chunk, Turn
    from library.rag import RAGUnavailable, answer_question

    user = get_user_model().objects.get(username="demo")
    acceptance = user.document_set.get(filename="acceptance.xlsx")
    previous = Turn(question="خلاصهٔ سند پذیرش", sources=[{"title": acceptance.title, "document_id": acceptance.pk}])
    # For each case, check the expected content plus the exact set of cited files
    # where a single document (or pair of related documents) answers the question.
    cases = [
        ("model", "تو چه مدلی هستی", [], ["خودکار"], set()),
        ("greeting", "سلام", [], ["سلام"], set()),
        ("languages", "چند تا از اسناد فقط انگلیسی هست و کدام هم فارسی هم انگلیسی؟", [],
         ["فارسی (5)", "انگلیسی (5)", "فارسی و انگلیسی (5)"], None),
        ("relationships", "این سند با چه سندهایی مرتبط هست؟", [previous], ["transfer.jpg", "search-policy.txt"],
         {"acceptance.xlsx", "transfer.jpg", "search-policy.txt"}),
        ("missing evidence", "بودجه ZEBRA-909 چقدر است؟", [], ["پیدا نکردم"], set()),
        ("table lookup", "برای OCR-614 چند صفحه ثبت شده؟ به انگلیسی جواب بده", [], ["48", "page"], {"acceptance.xlsx"}),
        ("formats", "Which formats does ALF-27 accept? Answer in English.", [], ["png", "jpeg"], {"alefba-pilot.docx"}),
    ]
    passed = 0
    for label, question, history, expected, files in cases:
        try:
            answer, sources = answer_question(user, history, question)
        except RAGUnavailable:
            print(f"UNAVAILABLE  {label}")
            continue
        cited = set(user.document_set.filter(pk__in=[s["document_id"] for s in sources]).values_list("filename", flat=True))
        grounded = all(Chunk.objects.filter(document__owner=user, document_id=s["document_id"],
                                            location=s["location"], text__contains=s["quote"]).exists() for s in sources)
        correct = all(term.casefold() in answer.casefold() for term in expected)
        ok = grounded and correct and (files == cited if files is not None else len(cited) == 15)
        passed += ok
        print(f"{'PASS' if ok else 'FAIL'}  {label}")
    print(f"{passed}/{len(cases)}")
    return passed == len(cases)


if __name__ == "__main__":
    with TemporaryDirectory() as data:
        shutil.copyfile(ROOT / "demo/database.sqlite3", Path(data) / "db.sqlite3")
        os.environ.update(DATA_DIR=data, DJANGO_SETTINGS_MODULE="config.settings")
        import django
        django.setup()
        from django.core.management import call_command
        from django.db import connections
        try:
            call_command("migrate", verbosity=0)
            success = evaluate()
        finally:
            connections.close_all()
    sys.exit(0 if success else 1)
