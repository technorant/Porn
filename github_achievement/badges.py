"""Best-effort evidence from public profile badge elements, never inferred from counts."""
import re
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, build_opener

from .api import NoRedirect
from .catalog import ACHIEVEMENTS


class ProfileParser(HTMLParser):
    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self, account):
        super().__init__(convert_charrefs=True)
        self.account = account.lower()
        self.stack = []
        self.visible = set()
        self.profile = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "meta" and attrs.get("name") == "octolytics-dimension-user_login":
            self.profile |= attrs.get("content", "").lower() == self.account
        if tag == "meta" and attrs.get("property") == "og:url":
            self.profile |= attrs.get("content", "").rstrip("/").lower() == f"https://github.com/{self.account}"
        blocked = (self.stack[-1][1] if self.stack else False) or "markdown-body" in attrs.get("class", "").split() or tag in {"script", "template"}
        candidate = self.stack[-1][2] if self.stack else None
        if tag == "a":
            candidate = None
            link = urlsplit(attrs.get("href") or "")
            query = parse_qs(link.query)
            slug = (query.get("achievement") or [None])[0]
            if (link.netloc in {"", "github.com"} and link.path.rstrip("/").lower() == f"/{self.account}"
                    and query.get("tab") == ["achievements"] and slug in ACHIEVEMENTS):
                candidate = slug
        if tag == "img" and not blocked and candidate:
            source = urlsplit(attrs.get("src") or "")
            prefix = f"/images/modules/profile/achievements/{candidate}-"
            fingerprinted = (source.path.startswith(f"/assets/{candidate}-")
                             and source.path.endswith((".png", ".svg", ".webp")))
            if source.netloc == "github.githubassets.com" and (source.path.startswith(prefix) or fingerprinted):
                self.visible.add(candidate)
        if tag not in self.VOID:
            self.stack.append((tag, blocked, candidate))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                return


def fetch_profile(account, *, opener=None):
    # Intentionally never sends API tokens or authenticated cookies to the website.
    request = Request(f"https://github.com/{account}?tab=achievements", headers={
        "User-Agent": "github-achievement-python/0.2.0", "Accept": "text/html",
    })
    with (opener or build_opener(NoRedirect())).open(request, timeout=15) as response:
        return response.read(4_000_000).decode("utf-8", errors="replace")


def check_badges(account, selected=None, *, wait=0, fetch=fetch_profile, sleep=time.sleep, clock=time.monotonic, report=None):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}", account):
        raise ValueError("Enter a GitHub username, not a URL.")
    if not 0 <= wait <= 600:
        raise ValueError("Badge wait must be between 0 and 600 seconds.")
    selected = list(selected or ACHIEVEMENTS)
    if any(slug not in ACHIEVEMENTS for slug in selected):
        raise ValueError("Unknown achievement.")
    deadline = clock() + wait
    while True:
        note = "Only badges visible on the public profile can be confirmed; tier levels are not inferred."
        statuses = {slug: "unknown" for slug in selected}
        try:
            parser = ProfileParser(account)
            parser.feed(fetch(account))
            if parser.profile:
                statuses = {slug: "visible" if slug in parser.visible else "not_visible" for slug in selected}
                if "not_visible" in statuses.values():
                    note = "Some badges are not visible yet. They may be delayed, hidden, or unearned. No extra operations were created."
            else:
                note = "Could not recognize the public profile markup. Badge status is unknown."
        except (HTTPError, URLError, TimeoutError, OSError, HTTPException) as exc:
            if isinstance(exc, HTTPError):
                exc.close()
            note = "Could not reach the public GitHub profile. Badge status is unknown; retry the check later."
        result = {"account": account, "profile_url": f"https://github.com/{account}?tab=achievements",
                  "checked_at": datetime.now(timezone.utc).isoformat(), "badges": statuses, "note": note}
        if all(status == "visible" for status in statuses.values()) or clock() >= deadline:
            return result
        if report:
            report("Waiting for GitHub to display the badge; no new writes")
        sleep(min(15, max(0, deadline - clock())))
