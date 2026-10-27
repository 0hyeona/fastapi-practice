import base64
import os
import unittest
from email import policy
from email.parser import BytesParser
from unittest.mock import patch

import httpx

from app.services.email_service import EmailDeliveryError, send_reset_code

TOKEN_URL = "https://oauth2.googleapis.com/token"
SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"


class EmailServiceTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {
            "GMAIL_CLIENT_ID": "test-client",
            "GMAIL_CLIENT_SECRET": "test-secret",
            "GMAIL_REFRESH_TOKEN": "test-refresh",
            "GMAIL_FROM_EMAIL": "sender@gmail.com",
        })
        self.env.start()
        self.addCleanup(self.env.stop)

    def response(self, url, status=200, **kwargs):
        return httpx.Response(status, request=httpx.Request("POST", url), **kwargs)

    def test_missing_settings_do_not_send(self):
        for key in ("GMAIL_CLIENT_ID", "GMAIL_CLIENT_SECRET", "GMAIL_REFRESH_TOKEN", "GMAIL_FROM_EMAIL"):
            with self.subTest(key=key), patch.dict(os.environ, {key: " "}):
                with patch("app.services.email_service.httpx.Client") as factory:
                    with self.assertRaises(EmailDeliveryError):
                        send_reset_code("user@example.com", "012345")
                    factory.assert_not_called()

    def test_refresh_then_send_mime_message_to_other_recipient(self):
        with patch("app.services.email_service.httpx.Client") as factory:
            client = factory.return_value.__enter__.return_value
            client.post.side_effect = [
                self.response(TOKEN_URL, json={"access_token": "access-secret"}),
                self.response(SEND_URL, json={"id": "message-id"}),
            ]
            send_reset_code("other@example.com", "012345")
            refresh, send = client.post.call_args_list
            self.assertEqual(refresh.args, (TOKEN_URL,))
            self.assertEqual(refresh.kwargs["data"], {
                "client_id": "test-client", "client_secret": "test-secret",
                "refresh_token": "test-refresh", "grant_type": "refresh_token",
            })
            self.assertEqual(send.args, (SEND_URL,))
            self.assertEqual(send.kwargs["headers"]["Authorization"], "Bearer access-secret")
            message = BytesParser(policy=policy.default).parsebytes(
                base64.urlsafe_b64decode(send.kwargs["json"]["raw"]))
            self.assertEqual(message["From"], "sender@gmail.com")
            self.assertEqual(message["To"], "other@example.com")
            self.assertIn("012345", message.get_content())
            self.assertEqual(factory.call_args.kwargs["timeout"], 10.0)

    def test_refresh_failure_never_sends_email(self):
        for response in (
            self.response(TOKEN_URL, 400, json={"error": "invalid_grant"}),
            self.response(TOKEN_URL, json={}),
            self.response(TOKEN_URL, json=[]),
            self.response(TOKEN_URL, json={"access_token": 123}),
            self.response(TOKEN_URL, text="invalid json"),
        ):
            with self.subTest(response=response), patch("app.services.email_service.httpx.Client") as factory:
                client = factory.return_value.__enter__.return_value
                client.post.return_value = response
                with self.assertRaises(EmailDeliveryError) as error:
                    send_reset_code("user@example.com", "012345")
                self.assertEqual(client.post.call_count, 1)
                self.assertNotIn("invalid_grant", str(error.exception))

    def test_send_errors_and_invalid_responses_become_delivery_errors(self):
        for response in (
            self.response(SEND_URL, 403, json={"error": "private details"}),
            self.response(SEND_URL, 429),
            self.response(SEND_URL, 500),
            self.response(SEND_URL, json={}),
            self.response(SEND_URL, text="invalid json"),
        ):
            with self.subTest(status=response.status_code), patch("app.services.email_service.httpx.Client") as factory:
                client = factory.return_value.__enter__.return_value
                client.post.side_effect = [self.response(TOKEN_URL, json={"access_token": "access-secret"}), response]
                with self.assertRaises(EmailDeliveryError) as error:
                    send_reset_code("user@example.com", "012345")
                for secret in ("private details", "012345", "access-secret", "test-refresh"):
                    self.assertNotIn(secret, str(error.exception))

    def test_timeouts_at_either_stage_become_delivery_errors(self):
        for stage in (0, 1):
            with self.subTest(stage=stage), patch("app.services.email_service.httpx.Client") as factory:
                client = factory.return_value.__enter__.return_value
                responses = [self.response(TOKEN_URL, json={"access_token": "access-secret"})] if stage else []
                client.post.side_effect = responses + [httpx.ReadTimeout("timeout")]
                with self.assertRaises(EmailDeliveryError):
                    send_reset_code("user@example.com", "012345")

    def test_failure_log_identifies_stage_without_secrets(self):
        with patch("app.services.email_service.httpx.Client") as factory:
            client = factory.return_value.__enter__.return_value
            client.post.return_value = self.response(TOKEN_URL, 400, json={
                "error": "invalid_grant", "error_description": "private-secret-012345",
            })
            with self.assertLogs("app.services.email_service", level="ERROR") as logs:
                with self.assertRaises(EmailDeliveryError):
                    send_reset_code("user@example.com", "012345")
            output = " ".join(logs.output)
            self.assertIn("stage=token status=400 reason=invalid_grant", output)
            for secret in ("private-secret", "012345", "test-refresh", "test-secret", "user@example.com"):
                self.assertNotIn(secret, output)
