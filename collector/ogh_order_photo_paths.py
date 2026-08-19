"""Map mview_mon_op_prod.url onto the read-only Заказы CIFS share."""

from __future__ import annotations

from pathlib import Path

ZAKAZY_MARKER = "заказы"
PHOTO_SUBDIR = ("02_Поле", "Фото")


class ZakazyPathError(ValueError):
    """url cannot be mapped onto the Заказы share."""


def _as_windows(url: str) -> str:
    return url.replace("/", "\\")


def relpath_after_zakazy(url: str | None) -> str:
    """Return POSIX-ish relative path after the Заказы segment."""
    if url is None:
        raise ZakazyPathError("empty url")
    text = str(url).strip()
    if not text:
        raise ZakazyPathError("empty url")

    windows = _as_windows(text)
    lowered = windows.lower()
    idx = lowered.find(ZAKAZY_MARKER)
    if idx < 0:
        raise ZakazyPathError("url has no Заказы segment")

    after = windows[idx + len(ZAKAZY_MARKER) :].lstrip("\\")
    if not after:
        raise ZakazyPathError("url ends at Заказы")

    parts = [part for part in after.replace("\\", "/").split("/") if part]
    if any(part in (".", "..") for part in parts):
        raise ZakazyPathError("path traversal")
    return "/".join(parts)


def photo_dir_for_url(url: str | None, root: Path) -> Path:
    """Resolve url to <root>/<rel>/02_Поле/Фото, staying inside root."""
    rel = relpath_after_zakazy(url)
    photo_dir = (root / rel).joinpath(*PHOTO_SUBDIR)
    resolved_root = root.resolve()
    resolved_photo = photo_dir.resolve()
    try:
        resolved_photo.relative_to(resolved_root)
    except ValueError as exc:
        raise ZakazyPathError("path escapes share root") from exc
    return photo_dir


def file_relpath(photo_dir: Path, photo: Path, root: Path) -> str:
    """Relative path of one photo from the Заказы root (unique log key)."""
    return photo.resolve().relative_to(root.resolve()).as_posix()
