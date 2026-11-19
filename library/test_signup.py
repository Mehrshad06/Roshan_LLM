from django.contrib.auth import get_user_model
from django.test import TestCase


class SignupTests(TestCase):
    def test_signup_logs_in_with_a_private_empty_workspace(self):
        payload = {"username": "reader", "password1": "Long-reader-468!", "password2": "Long-reader-468!"}
        self.assertContains(self.client.get("/accounts/login/"), "/accounts/signup/")
        self.assertRedirects(self.client.post("/accounts/signup/", payload), "/")
        self.assertEqual(self.client.get("/api/documents/").json(), [])
        self.assertFalse(get_user_model().objects.get(username="reader").is_staff)
        self.client.logout()
        result = self.client.post("/accounts/signup/", {**payload, "username": "READER"})
        self.assertIn("username", result.context["form"].errors)
        self.assertEqual(get_user_model().objects.count(), 1)
