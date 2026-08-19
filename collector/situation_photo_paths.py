"""Map mview_mon_op_files.fnm onto the read-only situation CIFS share."""

from __future__ import annotations

from pathlib import Path

from collector.genplan_photo_exif import is_photo_file


class SituationPathError(ValueError):
    """fnm cannot be mapped onto the situation share."""


def relpath_from_fnm(fnm: str | None) -> str:
    """Return POSIX-ish relative path from situation root."""
    if fnm is None:
        raise SituationPathError("empty fnm")
    text = str(fnm).strip()
    if not text:
        raise SituationPathError("empty fnm")

    posix = text.replace("\\", "/")
    if posix.startswith("/") or (len(posix) >= 2 and posix[1] == ":"):
        raise SituationPathError("absolute path")

    parts = [part for part in posix.split("/") if part]
    if not parts:
        raise SituationPathError("empty fnm")
    if any(part in (".", "..") for part in parts):
        raise SituationPathError("path traversal")
    return "/".join(parts)


def path_for_fnm(fnm: str | None, root: Path) -> Path:
    """Resolve fnm under root, staying inside the share."""
    rel = relpath_from_fnm(fnm)
    path = root / rel
    resolved_root = root.resolve()
    resolved = path.resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise SituationPathError("path escapes share root") from exc
    return path


def photos_for_fnm(fnm: str | None, root: Path) -> list[Path]:
    """fnm may be a photo file or a directory of photos."""
    path = path_for_fnm(fnm, root)
    if path.is_dir():
        return [item for item in sorted(path.iterdir()) if is_photo_file(item)]
    if is_photo_file(path):
        return [path]
    return []


def file_relpath(photo: Path, root: Path) -> str:
    return photo.resolve().relative_to(root.resolve()).as_posix()
