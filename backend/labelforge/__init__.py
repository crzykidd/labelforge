from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _version

try:
    __version__ = _version("labelforge")
except PackageNotFoundError:  # running from a source tree, not pip-installed
    __version__ = "unknown"
