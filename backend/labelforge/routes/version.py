import logging
import time
import urllib.error
import urllib.request
from json import JSONDecodeError
from json import loads as json_loads
from typing import Any

from fastapi import APIRouter

from labelforge.bootstrap import __version__
from labelforge import settings_store

router = APIRouter()
logger = logging.getLogger(__name__)

_GITHUB_URL = "https://api.github.com/repos/crzykidd/labelforge/releases/latest"
_TTL_SECONDS = 6 * 3600  # 6 hours

# Module-level cache: {"result": {...}, "fetched_at": float}
_cache: dict[str, Any] = {}


def _parse_semver(v: str) -> tuple[int, ...] | None:
    """Parse a dotted numeric version string, tolerating a leading 'v'.

    Returns a tuple of ints (major, minor, patch) or None if unparseable.
    """
    v = v.strip().lstrip("v")
    parts = v.split(".")
    try:
        return tuple(int(p) for p in parts if p)
    except ValueError:
        return None


def _is_newer(latest: str, current: str) -> bool:
    """Return True if latest > current. False if either is unparseable."""
    l = _parse_semver(latest)
    c = _parse_semver(current)
    if l is None or c is None:
        return False
    # Pad to equal length for comparison
    length = max(len(l), len(c))
    l_padded = l + (0,) * (length - len(l))
    c_padded = c + (0,) * (length - len(c))
    return l_padded > c_padded


def _fetch_github() -> dict[str, Any]:
    """Call the GitHub releases API and return parsed fields.

    On any network/parse error, raises an exception — callers handle it.
    """
    req = urllib.request.Request(
        _GITHUB_URL,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "labelforge",
        },
    )
    with urllib.request.urlopen(req, timeout=3) as resp:
        body = json_loads(resp.read().decode())

    tag_name: str = body.get("tag_name", "")
    latest = tag_name.lstrip("v")
    return {
        "latest": latest or None,
        "release_url": body.get("html_url"),
        "release_name": body.get("name"),
        "release_notes": body.get("body"),
    }


def _refresh_cache() -> None:
    """Attempt to refresh the in-memory cache from GitHub.

    On failure, logs a warning and leaves the existing cache entry intact
    (so a stale-but-good value continues to be served).
    """
    try:
        data = _fetch_github()
        _cache["result"] = data
        _cache["fetched_at"] = time.monotonic()
        logger.debug("GitHub release check succeeded: latest=%s", data.get("latest"))
    except (urllib.error.URLError, TimeoutError, JSONDecodeError, KeyError, OSError) as exc:
        logger.warning("GitHub release check failed: %s", exc)


def _cached_github() -> dict[str, Any]:
    """Return the cached GitHub result, refreshing if stale or absent."""
    now = time.monotonic()
    fetched_at = _cache.get("fetched_at")
    if fetched_at is None or (now - fetched_at) > _TTL_SECONDS:
        _refresh_cache()
    return _cache.get("result") or {}


@router.get("/version")
async def get_version() -> dict:
    current = __version__
    check_enabled = settings_store.get("update_check_enabled")

    if not check_enabled:
        return {
            "current": current,
            "latest": None,
            "update_available": False,
            "release_url": None,
            "release_name": None,
            "release_notes": None,
            "checked": False,
        }

    gh = _cached_github()
    latest = gh.get("latest")
    update_available = _is_newer(latest, current) if latest else False

    return {
        "current": current,
        "latest": latest,
        "update_available": update_available,
        "release_url": gh.get("release_url"),
        "release_name": gh.get("release_name"),
        "release_notes": gh.get("release_notes"),
        "checked": True,
    }
