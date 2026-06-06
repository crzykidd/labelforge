# Import paths verified against brother-ql-inventree 1.3:
#   brother_ql.raster.BrotherQLRaster               — builds the instruction buffer
#   brother_ql.conversion.convert                   — PIL Image → raster bytes (returns qlr.data)
#   brother_ql.backends.helpers.send                — transmits bytes to the printer
#   brother_ql.backends.helpers.backend_factory     — returns {"backend_class": ..., ...}
#   brother_ql.reader.interpret_response            — parses 32-byte status reply into dict
#   brother_ql.labels.ALL_LABELS                    — list of Label objects;
#     .tape_size, .identifier, .color
#
# Network backend expects printer_identifier in the form "tcp://host[:port]"
# (port defaults to 9100 when omitted).  The send() helper also accepts
# backend_identifier values: "network", "linux_kernel", "pyusb".
#
# get_printer() raises NotImplementedError for backend="network" (library design).
# Bypass by instantiating BrotherQLBackendNetwork directly via backend_factory.

import html.parser
import logging
import re
import urllib.request

from brother_ql.backends.helpers import backend_factory, send
from brother_ql.conversion import convert
from brother_ql.labels import ALL_LABELS
from brother_ql.raster import BrotherQLRaster
from brother_ql.reader import interpret_response
from PIL import Image

logger = logging.getLogger(__name__)

# Centralized threshold — must match the value passed to convert() so that
# to_print_bitmap() and print_image() apply the exact same 1-bit decision.
PRINT_THRESHOLD = 70  # percent, same semantics as convert()'s threshold= kwarg
_THRESHOLD_PX: int = min(255, max(0, int((100.0 - PRINT_THRESHOLD) / 100.0 * 255)))
# Original L pixels ≤ this value print as black; above it → white (no ink).
_PRINT_CUTOFF: int = 255 - _THRESHOLD_PX


def to_print_bitmap(image: Image.Image) -> Image.Image:
    """Reproduce convert()'s 1-bit threshold on *image*.

    Returns a mode-'L' image (0 = will print black, 255 = will not print)
    that is the exact bitmap the printer rasterizes.  Use this for preview
    responses so preview == print for every element type.
    """
    im = image.convert("L")
    return im.point(lambda x: 0 if x <= _PRINT_CUTOFF else 255)


class PrintError(Exception):
    pass


class StatusUnavailable(Exception):
    pass


def _media_id_from_dims(width_mm: int, length_mm: int, tape_color_raw: int | None) -> str | None:
    matches = [lbl for lbl in ALL_LABELS if lbl.tape_size == (width_mm, length_mm)]
    if not matches:
        return None
    if len(matches) == 1:
        return matches[0].identifier
    # Multiple labels share the same tape_size (e.g. "62" and "62red" are both (62, 0)).
    # Tape color is NOT recoverable: Brother's status spec leaves bytes 24-31 reserved
    # (00h) and exposes no color field, so tape_color_raw is meaningless here. We default
    # to mono "62"; the user selects "62red" manually and media_compatible() treats
    # same-dimension rolls as compatible. See docs/decisions.md (2026-05-31, two-color DK).
    _ = tape_color_raw  # always 00h per spec — kept for signature stability
    return "62"


def _color_capable(media_id: str | None) -> bool:
    if media_id is None:
        return False
    lbl = next((lbl for lbl in ALL_LABELS if lbl.identifier == media_id), None)
    return bool(lbl and int(getattr(lbl, "color", 0) or 0))


class _StatusPageParser(html.parser.HTMLParser):
    """Extract dt/dd key-value pairs from the printer's status.html page."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.pairs: dict[str, str] = {}
        self._in_dt = False
        self._in_dd = False
        self._cur_dt: str | None = None
        self._buf: str = ""

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag == "dt":
            self._in_dt = True
            self._in_dd = False
            self._buf = ""
        elif tag == "dd":
            self._in_dd = True
            self._in_dt = False
            self._buf = ""

    def handle_endtag(self, tag: str) -> None:
        if tag == "dt":
            self._cur_dt = self._buf.strip()
            self._in_dt = False
        elif tag == "dd":
            if self._cur_dt:
                self.pairs[self._cur_dt] = self._buf.strip()
            self._cur_dt = None
            self._in_dd = False

    def handle_data(self, data: str) -> None:
        if self._in_dt or self._in_dd:
            self._buf += data


def media_compatible(loaded_id: str, expected_id: str) -> bool:
    """Return True when the loaded media can print the expected layout.

    Color-variant rolls of identical physical size (e.g. "62" and "62red", both
    62mm continuous) are indistinguishable from the status read's dimensions
    alone — the printer doesn't reliably report tape color over TCP/HTTP — so we
    don't block on the color guess. The printer itself is the final authority on
    a true media mismatch. Differing physical sizes (e.g. 62 vs 29) still block.
    """
    if loaded_id == expected_id:
        return True
    loaded = next((lbl for lbl in ALL_LABELS if lbl.identifier == loaded_id), None)
    expected = next((lbl for lbl in ALL_LABELS if lbl.identifier == expected_id), None)
    if loaded is not None and expected is not None and loaded.tape_size == expected.tape_size:
        return True
    return False


def status_read(host: str, backend: str, timeout_ms: int = 2000) -> dict:
    """Query printer status over TCP (primary) or HTTP (fallback).

    Returns:
        {
          "ready": bool,
          "model": str | None,
          "media_id": str | None,   # e.g. "62", "62x29", "62red"
          "width_mm": int | None,
          "length_mm": int | None,  # 0 for continuous
          "color_capable": bool,
          "errors": list[str],
          "source": "tcp" | "http",
        }
    Raises StatusUnavailable if both paths fail or backend != "network".
    """
    if backend != "network":
        raise StatusUnavailable(
            f"Printer status check only supported for network backend (got '{backend}')"
        )

    timeout_s = timeout_ms / 1000
    raw: bytes = b""
    width_mm: int | None = None
    length_mm: int | None = None

    # Primary: raw TCP ESC i S (may return empty on some firmware — HTTP fallback handles it)
    try:
        be = backend_factory("network")
        printer = None
        try:
            printer = be["backend_class"](f"tcp://{host}")
            printer.read_timeout = timeout_s
            printer.s.settimeout(timeout_s)
            printer.write(b"\x1b\x69\x53")
            raw = printer.read(32)
        finally:
            if printer is not None:
                try:
                    printer.s.close()
                except Exception as exc:
                    logger.debug("Failed to close printer socket cleanly: %s", exc)
    except Exception as exc:
        logger.debug("TCP status path failed: %s", exc)

    # Diagnostic: dumps the raw ESC i S status response as hex. Only emitted when
    # LOG_LEVEL=DEBUG. Handy for inspecting undocumented bytes (e.g. probing
    # whether a byte encodes tape color); see docs/features/printer-status.md.
    logger.debug("TCP status raw (%d bytes): %s", len(raw), raw.hex())
    if len(raw) >= 32:
        try:
            parsed = interpret_response(raw)
            width_mm = int(parsed.get("media_width", 0) or 0)
            length_mm = int(parsed.get("media_length", 0) or 0)
            tape_color_raw = raw[24]
            media_id = _media_id_from_dims(width_mm, length_mm, tape_color_raw)
            errors_list = [str(e) for e in (parsed.get("errors") or [])]
            return {
                "ready": not errors_list,
                "model": str(parsed.get("model") or "") or None,
                "media_id": media_id,
                "width_mm": width_mm or None,
                "length_mm": length_mm,
                "color_capable": _color_capable(media_id),
                "errors": errors_list,
                "source": "tcp",
            }
        except Exception as exc:
            logger.debug("TCP response parse failed: %s", exc)

    # Fallback: HTTP status page (unauthenticated, no readback limitation)
    try:
        url = f"http://{host}/general/status.html"
        with urllib.request.urlopen(url, timeout=timeout_s) as resp:
            html_content = resp.read().decode("utf-8", errors="replace")

        parser = _StatusPageParser()
        parser.feed(html_content)

        device_status = parser.pairs.get("Device Status", "")
        media_type_str = parser.pairs.get("Media Type", "")
        ready = "READY" in device_status.upper()

        width_mm = None
        length_mm = None
        if media_type_str:
            m = re.search(r"(\d+)mm\s*x\s*(\d+)mm", media_type_str, re.IGNORECASE)
            if m:
                width_mm = int(m.group(1))
                length_mm = int(m.group(2))
            else:
                m2 = re.search(r"(\d+)mm", media_type_str, re.IGNORECASE)
                if m2:
                    width_mm = int(m2.group(1))
                    length_mm = 0

        media_id = (
            _media_id_from_dims(width_mm, length_mm, None)
            if width_mm is not None and length_mm is not None
            else None
        )
        return {
            "ready": ready,
            "model": None,
            "media_id": media_id,
            "width_mm": width_mm,
            "length_mm": length_mm,
            "color_capable": _color_capable(media_id),
            "errors": [],
            "source": "http",
        }
    except Exception as exc:
        logger.debug("HTTP status path failed: %s", exc)
        raise StatusUnavailable(f"Printer did not respond: {exc}") from exc


def print_image(
    image: Image.Image,
    label_media: str,
    model: str,
    backend: str,
    host: str,
) -> str:
    """Convert *image* to raster instructions and send to the printer.

    Returns the send outcome string. NOTE: the network backend cannot read
    back from the printer, so it returns 'sent' (transmitted, result unknown)
    rather than 'printed' even on success. Only USB backends can confirm an
    actual print. Callers must not treat 'sent' as a guaranteed print.

    Raises PrintError on any failure so callers can surface a clean 500.
    """
    try:
        qlr = BrotherQLRaster(model)
        # Two-color media (e.g. "62red" / DK-2251) must be printed with red=True
        # even for black-only text: the job has to declare two-color media or the
        # printer rejects it as "wrong roll: check the print data". convert() reads
        # the red plane from an RGB image, so promote L→RGB; a black-on-white image
        # simply leaves the red plane empty.
        red = _color_capable(label_media)
        img = image.convert("RGB") if red else image
        # rotate=0: keep the rendered image's width (696px for 62mm) as the
        # print-head width. rotate='auto' (the library default) can flip a
        # wide continuous image into a geometry the printer reads as the wrong
        # roll type. The renderer already produces the correct orientation.
        instructions = convert(
            qlr, [img], label_media, cut=True, rotate="0", threshold=PRINT_THRESHOLD, red=red
        )
        identifier = f"tcp://{host}" if backend == "network" else host
        result = send(
            instructions=instructions,
            printer_identifier=identifier,
            backend_identifier=backend,
            blocking=True,
        )
        logger.debug("Print result: %s", result)
        if result.get("outcome") == "error":
            raise PrintError(f"Printer reported an error: {result}")
        return result.get("outcome", "unknown")
    except PrintError:
        raise
    except Exception as exc:
        raise PrintError(f"Print failed: {exc}") from exc
