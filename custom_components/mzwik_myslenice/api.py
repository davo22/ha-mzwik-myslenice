"""Client for the MZWiK Myślenice eBOK portal.

The portal is an AngularJS front-end over a Spring REST backend. Everything the
UI does goes through POST calls under /ebok/. Authentication is a form login
that sets a session cookie; the reCAPTCHA field exists in the payload but the
backend does not enforce it, so it is sent empty (mirroring the web UI, which
also submits it empty for logged-in flows).
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from datetime import date, datetime

import aiohttp

from .const import BASE_URL

_LOGGER = logging.getLogger(__name__)

TIMEOUT = aiohttp.ClientTimeout(total=30)

# eBOK dates look like "/Date(05-08-2026:00:00:00.000)/" -> DD-MM-YYYY.
_DATE_RE = re.compile(r"/Date\((\d{2})-(\d{2})-(\d{4}):")


class MzwikApiError(Exception):
    """Portal unreachable or returned something unexpected."""


class MzwikAuthError(MzwikApiError):
    """Login rejected (wrong client number or password)."""


def parse_ebok_date(value: str | None) -> date | None:
    """Parse the portal's "/Date(DD-MM-YYYY:...)/" format into a date."""
    if not value:
        return None
    m = _DATE_RE.search(value)
    if not m:
        return None
    day, month, year = (int(g) for g in m.groups())
    # Year 4000 is the portal's "not set / open ended" sentinel.
    if year >= 3000:
        return None
    try:
        return date(year, month, day)
    except ValueError:
        return None


@dataclass
class MzwikMeter:
    """One installed water meter (zamont) from findSimpleMyForWaterUse."""

    zamont_id: str
    serial: str
    point: str
    address: str
    ownership: str
    last_reading: float | None
    last_reading_date: date | None


@dataclass
class MzwikReading:
    """One meter reading (odczyt) from findFacade."""

    reading_date: date
    value: float  # wskazanie — cumulative dial value
    consumption: float  # zuzycie — consumed in this reading's period
    daily_average: float | None  # sredniaDobowa, as reported by the portal
    unit: str


class MzwikApiClient:
    """Talk to the eBOK portal on behalf of one client account."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session
        self._context_id: int | None = None

    async def _post(self, path: str, payload: dict, *, allow_redirect: bool = False):
        url = f"{BASE_URL}/{path}"
        try:
            async with self._session.post(
                url, json=payload, timeout=TIMEOUT, allow_redirects=allow_redirect
            ) as resp:
                if resp.status in (301, 302) and allow_redirect is False:
                    return None  # login success signals via redirect
                if resp.status == 401:
                    raise MzwikAuthError("Not authenticated")
                if resp.status != 200:
                    body = (await resp.text())[:200]
                    raise MzwikApiError(f"HTTP {resp.status} from {path}: {body}")
                return await resp.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise MzwikApiError(f"Cannot reach eBOK: {err}") from err

    async def async_login(self, username: str, password: str) -> None:
        """Log in and capture the account's context id (podmiotId).

        Unlike the JSON data endpoints, the login is a form POST
        (application/x-www-form-urlencoded) to /security/login?contextId=-1 and
        replies with a 302 that sets the session cookie. The captcha field is
        sent empty; the backend does not enforce it.
        """
        try:
            async with self._session.post(
                f"{BASE_URL}/security/login?contextId=-1",
                data={"username": username, "password": password, "captcha": ""},
                timeout=TIMEOUT,
                allow_redirects=False,
            ) as resp:
                if resp.status not in (200, 302):
                    raise MzwikApiError(f"HTTP {resp.status} from security/login")
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise MzwikApiError(f"Cannot reach eBOK: {err}") from err

        try:
            async with self._session.get(
                f"{BASE_URL}/security/getEbokUserFromSession", timeout=TIMEOUT
            ) as resp:
                text = await resp.text()
                if resp.status != 200:
                    raise MzwikApiError(
                        f"HTTP {resp.status} from getEbokUserFromSession: {text[:200]}"
                    )
                data = json.loads(text)
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise MzwikApiError(f"Cannot reach eBOK: {err}") from err
        except json.JSONDecodeError as err:
            raise MzwikApiError(f"Bad session response: {err}") from err

        user = (data or {}).get("user")
        if not user or not user.get("podmiotId"):
            info = (data or {}).get("info")
            raise MzwikAuthError(f"Login rejected (info={info})")
        self._context_id = user["podmiotId"]

    async def async_get_meters(self) -> list[MzwikMeter]:
        """List the account's active water meters."""
        if self._context_id is None:
            raise MzwikApiError("Not logged in")
        # Full field set mirroring the portal's own request — the Spring backend
        # binds several of these to Java primitives (booleans), so sending the
        # complete payload avoids binding errors from omitted fields.
        data = await self._post(
            "zamont/findSimpleMyForWaterUse",
            {
                "contextId": self._context_id,
                "contextPunktId": 0,
                "activeOnly": True,
                "hideMainMeters": False,
                "numerPunktu": "",
                "punktId": "",
                "wspolnotaId": "",
                "zamontIdForConnected": None,
                "ownedByInvestorOnly": False,
                "punktRozliczanyOnly": False,
                "punktNierozliczanyOnly": False,
                "podlicznikiOnly": False,
                "mainOnly": False,
                "lokalowy": False,
                "ogrodowy": False,
                "punktNadrzednyId": None,
                "superiorOnly": False,
                "zamontIdSprzezone": None,
                "offset": None,
                "limit": 100,
                "orderBy": [],
                "fieldCriterion": [],
                "kodTypMiejscaZam": "",
                "onlyRadioReading": False,
            },
        )
        meters: list[MzwikMeter] = []
        for item in data or []:
            meters.append(
                MzwikMeter(
                    zamont_id=str(item["id"]),
                    serial=str(item.get("numerFabryczny") or item["id"]),
                    point=str(item.get("numer") or item.get("punktId") or ""),
                    address=str(item.get("adres") or ""),
                    ownership=str(item.get("wlasnoscUrzadzenia") or ""),
                    last_reading=_as_float(item.get("ostatniOdczyt")),
                    last_reading_date=parse_ebok_date(item.get("dataOstatniegoOdczytu")),
                )
            )
        return meters

    async def async_get_readings(self, zamont_id: str, limit: int = 200) -> list[MzwikReading]:
        """Fetch readings for one meter, newest first from the portal."""
        if self._context_id is None:
            raise MzwikApiError("Not logged in")
        data = await self._post(
            "odczyt/findFacade",
            {
                "dataKon": None,
                "dataPocz": None,
                "zamontId": zamont_id,
                "punktId": None,
                "start": 0,
                "limit": limit,
                "order": "data_odczytu_DESC",
                "wspolnotaId": None,
                "contextId": self._context_id,
                "orderBy": [],
                "fieldCriterion": [],
            },
        )
        readings: list[MzwikReading] = []
        for item in data or []:
            d = parse_ebok_date(item.get("dataOdczytu"))
            if d is None:
                continue
            readings.append(
                MzwikReading(
                    reading_date=d,
                    value=_as_float(item.get("wskazanie")) or 0.0,
                    consumption=_as_float(item.get("zuzycie")) or 0.0,
                    daily_average=_as_float(item.get("sredniaDobowa")),
                    unit=str(item.get("jednMiary") or "m3"),
                )
            )
        return readings


def _as_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
