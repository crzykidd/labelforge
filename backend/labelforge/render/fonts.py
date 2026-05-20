import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

_SYSTEM_FONT_DIR = Path("/usr/share/fonts/truetype")
_EXTENSIONS = {".ttf", ".otf"}
# Style keyword tokens used to split family from style in filename stems.
_STYLE_TOKENS = {
    "Bold", "Italic", "Light", "Thin", "Medium", "Regular",
    "Black", "Condensed", "Oblique", "SemiBold", "ExtraBold",
}

_font_cache: list["FontInfo"] = []


@dataclass
class FontInfo:
    name: str   # filename stem — used as font identifier in the API
    path: str
    family: str
    style: str


def _parse_stem(stem: str) -> tuple[str, str]:
    """Split 'DejaVuSans-Bold' into family='DejaVu Sans', style='Bold'."""
    tokens = stem.replace("-", " ").replace("_", " ").split()
    style_parts = [t for t in tokens if t in _STYLE_TOKENS]
    family_parts = [t for t in tokens if t not in _STYLE_TOKENS]
    family = " ".join(family_parts) or stem
    style = " ".join(style_parts) or "Regular"
    return family, style


def _scan_dir(directory: Path, fonts: dict[str, FontInfo]) -> None:
    if not directory.exists():
        logger.debug("Font directory not found, skipping: %s", directory)
        return
    for path in sorted(directory.rglob("*")):
        if path.suffix.lower() in _EXTENSIONS and path.is_file():
            name = path.stem
            family, style = _parse_stem(name)
            fonts[name] = FontInfo(name=name, path=str(path), family=family, style=style)


def load_fonts(user_font_dir: Path) -> None:
    global _font_cache
    fonts: dict[str, FontInfo] = {}
    _scan_dir(_SYSTEM_FONT_DIR, fonts)
    # User fonts overlay system fonts on name collision.
    _scan_dir(user_font_dir, fonts)
    _font_cache = list(fonts.values())
    logger.info("Fonts loaded: %d fonts discovered", len(_font_cache))


def get_fonts() -> list[FontInfo]:
    return _font_cache


def get_font_path(name: str) -> str | None:
    for f in _font_cache:
        if f.name == name:
            return f.path
    return None


def reload_fonts(user_font_dir: Path) -> None:
    """Re-scan font directories. Not yet wired to an endpoint."""
    load_fonts(user_font_dir)
