from django.test import TestCase
from django.urls import reverse


class LegalPagesSmokeTests(TestCase):
    def test_legal_pages_render(self):
        urls = [
            reverse("helpcenter:terms"),
            reverse("helpcenter:privacy"),
            reverse("helpcenter:cookies"),
            reverse("helpcenter:acceptable_use"),
            reverse("helpcenter:security"),
            reverse("helpcenter:refund_policy"),
        ]
        for url in urls:
            resp = self.client.get(url)
            self.assertEqual(resp.status_code, 200, msg=f"Expected 200 for {url}, got {resp.status_code}")
