"""Small REST/GraphQL client. Ambiguous writes are never automatically replayed."""
import json
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from . import __version__


class GitHubError(RuntimeError):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class WriteLimiter:
    """Share this limiter between primary and helper clients."""
    def __init__(self, interval=8.0, *, clock=time.monotonic, sleep=time.sleep):
        self.interval, self.clock, self.sleep = interval, clock, sleep
        self.last = None

    def wait(self):
        if self.last is not None:
            delay = self.interval - (self.clock() - self.last)
            if delay > 0:
                self.sleep(delay)
        self.last = self.clock()


class GitHubClient:
    BASE = "https://api.github.com"

    def __init__(self, token, *, limiter=None, opener=None, sleep=time.sleep,
                 timeout=30, retries=2, max_wait=60):
        self._token = token
        self.limiter = limiter or WriteLimiter()
        self.opener = opener or build_opener(NoRedirect())
        self.sleep, self.timeout, self.retries, self.max_wait = sleep, timeout, retries, max_wait

    def _clean(self, text):
        return str(text).replace(self._token, "[REDACTED]") if self._token else str(text)

    def _retry_delay(self, headers, attempt):
        retry = headers.get("Retry-After")
        if retry:
            try:
                return max(0, float(retry))
            except ValueError:
                try:
                    return max(0, (parsedate_to_datetime(retry) - datetime.now(timezone.utc)).total_seconds())
                except (TypeError, ValueError):
                    pass
        if headers.get("X-RateLimit-Remaining") == "0":
            try:
                return max(1, float(headers["X-RateLimit-Reset"]) - time.time() + 1)
            except (ValueError, KeyError):
                pass
        return 2 ** (attempt + 1)

    def request(self, method, path, payload=None, *, read_only=False):
        if not path.startswith("/") or path.startswith("//"):
            raise ValueError("API paths must be relative to api.github.com.")
        read_only = read_only or method == "GET"
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        for attempt in range(self.retries + 1):
            if not read_only:
                self.limiter.wait()
            request = Request(self.BASE + path, data=data, method=method, headers={
                "Authorization": f"Bearer {self._token}",
                "Accept": "application/vnd.github+json",
                "Content-Type": "application/json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": f"github-achievement-python/{__version__}",
            })
            try:
                with self.opener.open(request, timeout=self.timeout) as response:
                    raw = response.read()
                if not raw:
                    return {}
                try:
                    return json.loads(raw)
                except (ValueError, UnicodeError) as exc:
                    raise GitHubError("GitHub returned invalid JSON; inspect remote state before retrying writes.") from exc
            except HTTPError as exc:
                try:
                    error = json.loads(exc.read())
                    message = error.get("message", "Request rejected") if isinstance(error, dict) else "Request rejected"
                except (ValueError, UnicodeError):
                    message = exc.reason
                finally:
                    exc.close()
                limited = exc.code == 429 or (exc.code == 403 and (
                    exc.headers.get("Retry-After") is not None
                    or exc.headers.get("X-RateLimit-Remaining") == "0"
                    or "rate limit" in str(message).lower()))
                retryable = limited or (read_only and exc.code >= 500)
                delay = self._retry_delay(exc.headers, attempt)
                if retryable and attempt < self.retries and delay <= self.max_wait:
                    self.sleep(delay)
                    continue
                hint = ""
                if limited:
                    hint = f" Rate limited; retry after at least {delay:.0f} seconds."
                elif exc.code == 401:
                    hint = " Check your token and its expiration."
                elif exc.code in (403, 404):
                    hint = " Check repository access, token permissions, and repository settings."
                elif not read_only and exc.code >= 500:
                    hint = " Write outcome is uncertain; inspect remote state before retrying."
                raise GitHubError(self._clean(f"GitHub HTTP {exc.code}: {message}.{hint}"), exc.code) from None
            except (URLError, TimeoutError, OSError, HTTPException) as exc:
                if read_only and attempt < self.retries:
                    self.sleep(2 ** (attempt + 1))
                    continue
                hint = "" if read_only else " Write outcome is uncertain; inspect remote state before retrying."
                raise GitHubError(self._clean(f"Could not reach GitHub: {exc}.{hint}")) from None
        raise AssertionError("Unreachable")

    def graphql(self, query, variables, *, mutation=False):
        response = self.request("POST", "/graphql", {"query": query, "variables": variables}, read_only=not mutation)
        if response.get("errors"):
            messages = "; ".join(item.get("message", "GraphQL error") for item in response["errors"])
            raise GitHubError(self._clean(f"GitHub GraphQL: {messages}"))
        if not response.get("data"):
            raise GitHubError("GitHub returned no GraphQL data.")
        return response["data"]
