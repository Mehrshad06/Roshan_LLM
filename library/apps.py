from django.utils.translation import gettext_lazy as gettext
from django.apps import AppConfig


class LibraryConfig(AppConfig):
    name = "library"
    verbose_name = gettext("کتابخانه اسناد")
