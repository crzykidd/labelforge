# Import paths verified against brother-ql-inventree 1.3:
#   brother_ql.raster.BrotherQLRaster       — builds the instruction buffer
#   brother_ql.conversion.convert           — PIL Image → raster bytes (returns qlr.data)
#   brother_ql.backends.helpers.send        — transmits bytes to the printer
#
# Network backend expects printer_identifier in the form "tcp://host[:port]"
# (port defaults to 9100 when omitted).  The send() helper also accepts
# backend_identifier values: "network", "linux_kernel", "pyusb".

import logging

from brother_ql.backends.helpers import send
from brother_ql.conversion import convert
from brother_ql.raster import BrotherQLRaster
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
        # rotate=0: keep the rendered image's width (696px for 62mm) as the
        # print-head width. rotate='auto' (the library default) can flip a
        # wide continuous image into a geometry the printer reads as the wrong
        # roll type. The renderer already produces the correct orientation.
        instructions = convert(qlr, [image], label_media, cut=True, rotate="0", threshold=PRINT_THRESHOLD)
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
