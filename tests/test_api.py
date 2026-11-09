import io
import json
from http.client import IncompleteRead
import unittest
from datetime import datetime, timezone
from email.utils import format_datetime
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
        if hasattr(response, "read"):
            return response
        return io.BytesIO(response if isinstance(response, bytes) else json.dumps(response).encode())


def response_with_headers(data, headers):
    response = io.BytesIO(json.dumps(data).encode())
    response.headers = headers
    return response


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

    def test_secondary_limit_waits_a_minute_then_backs_off(self):
        client, opener, sleeps = self.client(http_error(403, "secondary rate limit"), http_error(403, "secondary rate limit"), {"ok": True})
        client.request("POST", "/test", {})
        self.assertEqual(sleeps, [60, 120])
        self.assertEqual(len(opener.requests), 3)

    def test_secondary_limit_retries_are_bounded(self):
        client, opener, sleeps = self.client(*[http_error(429) for _ in range(3)])
        with self.assertRaises(GitHubError) as error:
            client.request("POST", "/test", {})
        self.assertEqual(sleeps, [60, 120])
        self.assertEqual(len(opener.requests), 3)
        self.assertEqual(error.exception.retry_after, 240)

    def test_primary_reset_and_retry_after_are_both_respected(self):
        client, _, sleeps = self.client(http_error(403, "rate limit", {
            "x-ratelimit-remaining": "0", "x-ratelimit-reset": "1030", "retry-after": "5"
        }), {}, clock=lambda: 1000)
        client.request("GET", "/test")
        self.assertEqual(sleeps, [31])

    def test_http_date_retry_after_is_supported(self):
        date = format_datetime(datetime.fromtimestamp(1045, timezone.utc), usegmt=True)
        client, _, sleeps = self.client(http_error(429, headers={"Retry-After": date}), {}, clock=lambda: 1000)
        client.request("GET", "/test")
        self.assertEqual(sleeps, [45])

    def test_successful_response_with_zero_quota_pauses_next_request(self):
        first = response_with_headers({"ok": True}, {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "1030"})
        client, _, sleeps = self.client(first, {}, clock=lambda: 1000)
        client.request("GET", "/first")
        self.assertEqual(sleeps, [])
        client.request("POST", "/next", {})
        self.assertEqual(sleeps, [31])

    def test_long_known_quota_wait_stops_before_sending_next_request(self):
        first = response_with_headers({}, {"x-ratelimit-remaining": "0", "x-ratelimit-reset": "2000"})
        client, opener, sleeps = self.client(first, clock=lambda: 1000)
        client.request("GET", "/first")
        with self.assertRaisesRegex(GitHubError, "1001 seconds"):
            client.request("POST", "/next", {})
        self.assertEqual(len(opener.requests), 1)
        self.assertEqual(sleeps, [])

    def test_graphql_http_200_rate_rejection_retries_after_reset(self):
        limited = response_with_headers({"data": {"create": None}, "errors": [{"type": "RATE_LIMITED", "message": "API rate limit exceeded"}]},
            {"x-ratelimit-remaining": "0", "x-ratelimit-reset": "1020", "x-ratelimit-resource": "graphql"})
        client, opener, sleeps = self.client(limited, {"data": {"create": {"id": "1"}}}, clock=lambda: 1000)
        result = client.graphql("mutation Create { create { id } }", {}, mutation=True)
        self.assertEqual(result, {"create": {"id": "1"}})
        self.assertEqual(sleeps, [21])
        self.assertEqual(len(opener.requests), 2)

    def test_graphql_partial_mutation_is_never_replayed_even_with_rate_error(self):
        client, opener, sleeps = self.client({"data": {"create": {"id": "1"}}, "errors": [{"type": "RATE_LIMITED", "message": "rate limit exceeded"}]})
        with self.assertRaises(GitHubError):
            client.graphql("mutation Create { create { id } }", {}, mutation=True)
        self.assertEqual(len(opener.requests), 1)
        self.assertEqual(sleeps, [])

    def test_malformed_retry_header_uses_safe_secondary_backoff(self):
        client, _, sleeps = self.client(http_error(429, headers={"Retry-After": "nan"}), {})
        client.request("GET", "/test")
        self.assertEqual(sleeps, [60])

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
