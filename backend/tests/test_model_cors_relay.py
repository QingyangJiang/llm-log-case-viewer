import unittest

from scripts.model_cors_relay import ALLOWED_REQUEST_HEADERS, RelayConfig, cors_headers


class ModelCorsRelayTest(unittest.TestCase):
    def setUp(self) -> None:
        self.config = RelayConfig(
            upstream="https://model.nioint.com/token-x/v1/messages",
            allowed_origin="http://10.129.72.139:8080",
            allow_no_origin=True,
        )

    def test_allows_only_the_configured_case_lens_origin(self) -> None:
        headers = cors_headers("http://10.129.72.139:8080", self.config)
        self.assertEqual(headers["Access-Control-Allow-Origin"], "http://10.129.72.139:8080")
        self.assertEqual(headers["Access-Control-Allow-Headers"], ALLOWED_REQUEST_HEADERS)
        self.assertEqual(cors_headers("https://example.com", self.config), {})

    def test_supports_private_network_preflight(self) -> None:
        headers = cors_headers("http://10.129.72.139:8080", self.config, private_network=True)
        self.assertEqual(headers["Access-Control-Allow-Private-Network"], "true")


if __name__ == "__main__":
    unittest.main()
