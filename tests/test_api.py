import base64
import unittest

from sdeck.api import token_from_headers


class ApiAuthTests(unittest.TestCase):
    def test_bearer_token(self) -> None:
        self.assertEqual(token_from_headers({"Authorization": "Bearer secret"}), "secret")

    def test_basic_password_token(self) -> None:
        encoded = base64.b64encode(b"sdeck:secret").decode()
        self.assertEqual(token_from_headers({"Authorization": f"Basic {encoded}"}), "secret")

    def test_custom_header(self) -> None:
        self.assertEqual(token_from_headers({"X-SDeck-Token": "secret"}), "secret")


if __name__ == "__main__":
    unittest.main()
