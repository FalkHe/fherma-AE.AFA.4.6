"""The `robots.txt` gate for the used-price research path (D8).

Reuses two already-landed pieces rather than inventing anything: the
process-wide politeness pacing (`fetch.PolitenessGate`) so a `robots.txt`
fetch counts against the same one-request-per-host budget as every other
request to that host, and the honest `fetch.USER_AGENT` — both the identity
`fetch.build_client()` already sends and the one this module's
`can_fetch(...)` checks are made under. Everything else is the **stdlib**
`urllib.robotparser` — this project takes on zero new dependencies for it
(hard rule, this phase).

Nothing here talks to the live web yet; 6.22 wires this gate into the price
fetch path only (D8 item 5 — landed ingestion is not touched).

Pinned outcome table (D8 item 2), decided once per host and cached for this
object's lifetime:

| `robots.txt` fetch result           | Outcome                                     |
|--------------------------------------|----------------------------------------------|
| HTTP 2xx                             | parsed; answer `parser.can_fetch(...)`        |
| HTTP 401 / 403                       | host disallowed (the stdlib convention)       |
| any other HTTP 4xx                   | host allowed (no robots policy published)     |
| HTTP 5xx / timeout / network error   | host disallowed (conservative)                |

`allows()` only ever returns a boolean. The caller (6.22) is the one that
prints the visible warning either way (D8 item 2) — this module logs one
`logger.warning` per refused host and nothing else.
"""

import logging
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx2

from app.services.ingestion import fetch

logger = logging.getLogger(__name__)


class RobotsGate:
    """Answers "may the price path fetch this URL?", one `robots.txt` per host."""

    def __init__(
        self,
        *,
        client: httpx2.AsyncClient,
        gate: fetch.PolitenessGate | None = None,
    ) -> None:
        self._client = client
        self._gate = gate if gate is not None else fetch.politeness
        # `None` means "this host is disallowed" (the 401/403/5xx/timeout/
        # network-error rows) — cached so a refused host is refused instantly
        # on every later call, without a second fetch.
        self._parsers: dict[str, RobotFileParser | None] = {}

    async def allows(self, url: str) -> bool:
        """Return whether `url` may be fetched under its host's `robots.txt`.

        The host's `robots.txt` is fetched at most once for this object's
        lifetime — cached per host (lower-cased, port dropped, via
        `fetch._host`), so a second URL on an already-checked host never
        triggers a second fetch.
        """
        host = fetch._host(url)
        if host not in self._parsers:
            self._parsers[host] = await self._fetch_parser(host, url)
        parser = self._parsers[host]
        if parser is None:
            return False
        return parser.can_fetch(fetch.USER_AGENT, url)

    async def _fetch_parser(self, host: str, url: str) -> RobotFileParser | None:
        """Fetch and parse one host's `robots.txt`, per the pinned outcome table."""
        robots_url = f"{urlsplit(url).scheme}://{host}/robots.txt"
        await self._gate.wait(host)
        try:
            response = await self._client.get(robots_url)
        except httpx2.TimeoutException:
            return self._refuse(host, f"Timed out fetching {robots_url}.")
        except httpx2.HTTPError as error:
            return self._refuse(host, f"Could not fetch {robots_url}: {type(error).__name__}.")

        if response.status_code in (401, 403):
            return self._refuse(
                host,
                f"{robots_url} answered HTTP {response.status_code}; disallowing the host.",
            )
        if 500 <= response.status_code < 600:
            return self._refuse(
                host,
                f"{robots_url} answered HTTP {response.status_code}; disallowing the host.",
            )

        parser = RobotFileParser()
        # `RobotFileParser.can_fetch` refuses everything until `.parse(...)`
        # has actually run once (it gates on `last_checked`, stdlib-internal
        # bookkeeping meant for `.read()`) — so the "any other 4xx" row must
        # call `.parse([])` explicitly, not merely skip parsing, to get the
        # "no policy published" `True` rather than a false "disallow".
        parser.parse(response.text.splitlines() if 200 <= response.status_code < 300 else [])
        return parser

    def _refuse(self, host: str, detail: str) -> None:
        """Log the one warning this module owns and return the "disallowed" marker."""
        logger.warning("Robots gate refusing host %s: %s", host, detail)
        return None
