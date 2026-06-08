"""Earliest startup wiring: logging + version.

Imported before anything that can fail (config, routers) so that import-time
errors — a missing required env var, a bad config — are visible in the logs
instead of producing a silent crash. Logging goes to stdout, unbuffered.
"""

import logging
import os
import sys
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version


def configure_logging() -> None:
    """Configure root logging to stdout. Idempotent (``force=True``).

    Called once on import (so config/import failures are logged) and again at
    lifespan start (so runtime logs survive uvicorn's own logging setup).
    """
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
        force=True,
    )


configure_logging()

try:
    __version__ = _pkg_version("labelforge")
except PackageNotFoundError:  # running from a source tree, not pip-installed
    __version__ = "unknown"

# Build markers baked in at image build time via Docker build args.
# The container has no .git, so runtime detection is not possible.
__channel__ = os.environ.get("LABELFORGE_CHANNEL", "release").strip() or "release"
__commit__: str | None = os.environ.get("LABELFORGE_COMMIT", "").strip() or None

logging.getLogger("labelforge").info(
    "labelforge %s — process starting (python %s) channel=%s commit=%s",
    __version__,
    sys.version.split()[0],
    __channel__,
    __commit__ or "unknown",
)
