from django.test import TestCase


class ScannerShieldTests(TestCase):
    def test_webhook_test_blocked(self):
        resp = self.client.post("/webhook-test/upload")
        # Middleware may return 404 or 410 depending on configuration.
        self.assertIn(resp.status_code, (404, 410))

    def test_env_probe_blocked(self):
        resp = self.client.get("/.env")
        self.assertIn(resp.status_code, (404, 410))
