"""Helpers for safely logging user-influenced values."""


def scrub(value: object) -> str:
    """Strip CR/LF from a value before it is interpolated into a log line.

    A user-controlled value written verbatim into a log can forge new log
    entries (CWE-117 / log injection) by smuggling newlines. Removing the
    line-break characters neutralises that without otherwise altering the value.
    """
    return str(value).replace("\r\n", "").replace("\r", "").replace("\n", "")
