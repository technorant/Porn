import io
import json
from http.client import IncompleteRead
import unittest
from urllib.error import HTTPError, URLError

from github_achievement.api import GitHubClient, GitHubError, NoRedirect, WriteLimiter


class FakeOpener:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    def open(self, request, timeout):
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return io.BytesIO(response if isinstance(response, bytes) else json.dumps(response).encode())


def http_error(code, message="Rejected", headers=None):
    return HTTPError("https://api.github.com/test", code, message, headers or {},
                     io.BytesIO(json.dumps({"message": message}).encode()))


class APITests(unittest.TestCase):
    def client(self, *responses, **kwargs):
        opener = FakeOpener(*responses)
        sleeps = []
        client = GitHubClient("secret-token", opener=opener, sleep=sleeps.append,
                              limiter=WriteLimiter(interval=0), **kwargs)
        return client, opener, sleeps

    def test_auth_json_and_version_headers(self):
        client, opener, _ = self.client({"number": 1})
        self.assertEqual(client.request("POST", "/test", {"body": "hello"}), {"number": 1})
        request = opener.requests[0]
        self.assertEqual(request.full_url, "https://api.github.com/test")
        self.assertEqual(request.get_header("Authorization"), "Bearer secret-token")
        self.assertEqual(request.get_header("X-github-api-version"), "2022-11-28")
        self.assertEqual(json.loads(request.data), {"body": "hello"})

    def test_empty_delete_response(self):
        client, _, _ = self.client(b"")
        self.assertEqual(client.request("DELETE", "/test"), {})

    def test_retry_read_server_error(self):
        client, opener, sleeps = self.client(http_error(503), {"ok": True})
        self.assertEqual(client.request("GET", "/test"), {"ok": True})
        self.assertEqual(len(opener.requests), 2)
        self.assertEqual(sleeps, [2])

    def test_never_replay_ambiguous_write(self):
        for error in (http_error(503), URLError("lost connection"), TimeoutError("timed out"), IncompleteRead(b"partial")):
            with self.subTest(error=type(error).__name__):
                client, opener, sleeps = self.client(error)
                with self.assertRaisesRegex(GitHubError, "uncertain"):
                    client.request("POST", "/test", {})
                self.assertEqual(len(opener.requests), 1)
                self.assertEqual(sleeps, [])

    def test_rate_limit_rejection_can_retry_write(self):
        client, opener, sleeps = self.client(http_error(429, headers={"Retry-After": "7"}), {"ok": True})
        client.request("POST", "/test", {})
        self.assertEqual(len(opener.requests), 2)
        self.assertEqual(sleeps, [7])

    def test_long_rate_limit_wait_stops(self):
        client, opener, sleeps = self.client(http_error(403, "rate limit exceeded", {"Retry-After": "3600"}))
        with self.assertRaisesRegex(GitHubError, "3600 seconds"):
            client.request("GET", "/test")
        self.assertEqual(len(opener.requests), 1)
        self.assertEqual(sleeps, [])

    def test_permission_denial_is_not_retried_and_secrets_are_redacted(self):
        client, opener, _ = self.client(http_error(403, "secret-token cannot access this resource"))
        with self.assertRaises(GitHubError) as error:
            client.request("POST", "/test", {})
        self.assertNotIn("secret-token", str(error.exception))
        self.assertIn("[REDACTED]", str(error.exception))
        self.assertEqual(len(opener.requests), 1)

    def test_read_network_retries_are_bounded(self):
        client, opener, sleeps = self.client(*[URLError("offline") for _ in range(3)])
        with self.assertRaises(GitHubError):
            client.request("GET", "/test")
        self.assertEqual(len(opener.requests), 3)
        self.assertEqual(sleeps, [2, 4])

    def test_graphql_error_is_not_success_or_replayed(self):
        client, opener, _ = self.client({"data": {"partial": True}, "errors": [{"message": "secret-token forbidden"}]})
        with self.assertRaisesRegex(GitHubError, "REDACTED"):
            client.graphql("mutation Example { test }", {}, mutation=True)
        self.assertEqual(len(opener.requests), 1)

    def test_invalid_json_is_actionable(self):
        client, _, _ = self.client(b"not JSON")
        with self.assertRaisesRegex(GitHubError, "inspect remote state"):
            client.request("POST", "/test", {})

    def test_absolute_paths_and_redirects_cannot_receive_token(self):
        client, opener, _ = self.client()
        for path in ("https://example.com", "//example.com"):
            with self.assertRaises(ValueError):
                client.request("GET", path)
        self.assertEqual(opener.requests, [])
        self.assertIsNone(NoRedirect().redirect_request(None, None, 302, "", {}, "https://example.com"))

    def test_shared_limiter_paces_both_clients(self):
        now = [0.0]
        sleeps = []

        def sleep(seconds):
            sleeps.append(seconds)
            now[0] += seconds

        limiter = WriteLimiter(clock=lambda: now[0], sleep=sleep)
        primary = GitHubClient("a", limiter=limiter, opener=FakeOpener({}))
        helper = GitHubClient("b", limiter=limiter, opener=FakeOpener({}))
        primary.request("POST", "/test", {})
        helper.request("PATCH", "/test", {})
        self.assertEqual(sleeps, [8])
