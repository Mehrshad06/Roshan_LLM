from django.contrib.auth import get_user_model
from django.test import TestCase


class InterfaceLanguageTests(TestCase):
    def test_language_switch_covers_workspace_admin_and_api(self):
        self.client.force_login(get_user_model().objects.create_superuser("reviewer"))
        for language, workspace, signout in [("en", "Document library", "Sign out"), ("fa", "کتابخانهٔ اسناد", "خروج")]:
            response = self.client.post("/i18n/setlang/", {"language": language, "next": "/api/docs/"})
            self.assertRedirects(response, "/api/docs/")
            self.assertContains(self.client.get("/"), workspace)
            self.assertContains(self.client.get("/"), signout)
            self.assertContains(self.client.get("/admin/"), 'name="language"')
            swagger = self.client.get("/api/docs/")
            self.assertContains(swagger, 'href="/"')
            self.assertContains(swagger, "SwaggerUIBundle")
