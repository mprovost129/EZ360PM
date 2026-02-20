from django.template import TemplateDoesNotExist
from django.template.loader import get_template
from django.test import TestCase, override_settings


class ErrorTemplateTests(TestCase):
    def test_404_template_exists(self):
        try:
            get_template("404.html")
        except TemplateDoesNotExist as exc:
            self.fail(f"404.html template missing: {exc}")

    def test_500_template_exists(self):
        try:
            get_template("500.html")
        except TemplateDoesNotExist as exc:
            self.fail(f"500.html template missing: {exc}")

    @override_settings(DEBUG=False, ALLOWED_HOSTS=["testserver"])
    def test_404_renders_custom_template_when_debug_false(self):
        resp = self.client.get("/definitely-not-a-real-page/")
        self.assertEqual(resp.status_code, 404)
        self.assertContains(resp, "Page not found", status_code=404)
