import unittest

from backend.jobs_executor import is_flow_auth_error


class FlowAuthErrorTests(unittest.TestCase):
    def test_detects_google_unauthenticated_response(self):
        error = ValueError(
            "Gagal generate image karakter di Google Flow (401): "
            "{'error': {'code': 401, 'status': 'UNAUTHENTICATED'}}"
        )
        self.assertTrue(is_flow_auth_error(error))

    def test_does_not_treat_quota_as_authentication_failure(self):
        self.assertFalse(is_flow_auth_error(RuntimeError("Quota Google Flow habis")))


if __name__ == "__main__":
    unittest.main()
