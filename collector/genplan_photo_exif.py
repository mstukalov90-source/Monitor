"""Extract upload metadata from photo EXIF and filename."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from fractions import Fraction
from pathlib import Path
from typing import Any, Optional

from PIL import ExifTags, Image

from collector.genplan_geom import is_valid_wgs84_pair

_DATE_FROM_FILENAME = re.compile(r"(\d{4}-\d{2}-\d{2})")
_PHOTO_SUFFIXES = frozenset({".jpg", ".jpeg", ".png"})


@dataclass(frozen=True)
class PhotoUploadMeta:
    date: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    azimuth_deg: Optional[float] = None

    def as_form_data(self) -> dict[str, str | float]:
        """Return only fields to send in multipart form (non-None)."""
        data: dict[str, str | float] = {}
        if self.date is not None:
            data["date"] = self.date
        if is_valid_wgs84_pair(self.lat, self.lng):
            data["lat"] = self.lat  # type: ignore[assignment]
            data["lng"] = self.lng  # type: ignore[assignment]
        if self.azimuth_deg is not None:
            data["azimuth_deg"] = self.azimuth_deg
        return data

    def as_db_payload(self) -> dict[str, Any]:
        """JSON-serializable dict with explicit nulls for missing fields."""
        return {
            "date": self.date,
            "lat": self.lat,
            "lng": self.lng,
            "azimuth_deg": self.azimuth_deg,
        }


def is_photo_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in _PHOTO_SUFFIXES


def photo_mime_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".png":
        return "image/png"
    return "image/jpeg"


def extract_photo_upload_meta(path: Path) -> PhotoUploadMeta:
    """Read date/coordinates/azimuth from EXIF; date fallback from filename."""
    date = _date_from_filename(path.name)
    lat: Optional[float] = None
    lng: Optional[float] = None
    azimuth_deg: Optional[float] = None

    try:
        with Image.open(path) as img:
            exif = img.getexif()
            if exif:
                exif_date = _date_from_exif(exif)
                if exif_date is not None:
                    date = exif_date
                lat, lng = _gps_from_exif(exif)
                azimuth_deg = _azimuth_from_exif(exif)
    except OSError:
        pass

    if not is_valid_wgs84_pair(lat, lng):
        lat, lng = None, None

    return PhotoUploadMeta(date=date, lat=lat, lng=lng, azimuth_deg=azimuth_deg)


def _date_from_filename(name: str) -> Optional[str]:
    match = _DATE_FROM_FILENAME.search(name)
    if not match:
        return None
    return match.group(1)


def _date_from_exif(exif: Any) -> Optional[str]:
    for tag_name in ("DateTimeOriginal", "DateTime"):
        raw = _exif_value(exif, tag_name)
        if not raw:
            continue
        parsed = _parse_exif_datetime(str(raw))
        if parsed is not None:
            return parsed
    return None


def _parse_exif_datetime(raw: str) -> Optional[str]:
    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(raw.strip(), fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _exif_value(exif: Any, tag_name: str) -> Any:
    for tag_id, value in exif.items():
        if ExifTags.TAGS.get(tag_id) == tag_name:
            return value
    return None


def _gps_ifd(exif: Any) -> dict[int, Any]:
    if hasattr(exif, "get_ifd"):
        gps_tag = getattr(ExifTags.IFD, "GPSInfo", 0x8825)
        try:
            ifd = exif.get_ifd(gps_tag)
            if ifd:
                return ifd
        except (KeyError, OSError, ValueError):
            pass
    gps_info = _exif_value(exif, "GPSInfo")
    return gps_info if isinstance(gps_info, dict) else {}


def _gps_tag(gps_ifd: dict[int, Any], name: str) -> Any:
    for tag_id, value in gps_ifd.items():
        if ExifTags.GPSTAGS.get(tag_id) == name:
            return value
    return None


def _gps_from_exif(exif: Any) -> tuple[Optional[float], Optional[float]]:
    gps_ifd = _gps_ifd(exif)
    if not gps_ifd:
        return None, None

    lat = _dms_to_decimal(
        _gps_tag(gps_ifd, "GPSLatitude"),
        _gps_tag(gps_ifd, "GPSLatitudeRef"),
    )
    lng = _dms_to_decimal(
        _gps_tag(gps_ifd, "GPSLongitude"),
        _gps_tag(gps_ifd, "GPSLongitudeRef"),
    )
    return lat, lng


def _azimuth_from_exif(exif: Any) -> Optional[float]:
    gps_ifd = _gps_ifd(exif)
    if not gps_ifd:
        return None
    raw = _gps_tag(gps_ifd, "GPSImgDirection")
    if raw is None:
        return None
    return _to_float(raw)


def _dms_to_decimal(
    dms: Any,
    ref: Any,
) -> Optional[float]:
    if not dms or ref is None:
        return None
    try:
        degrees = _to_float(dms[0])
        minutes = _to_float(dms[1])
        seconds = _to_float(dms[2])
    except (IndexError, TypeError, ValueError):
        return None
    if degrees is None or minutes is None or seconds is None:
        return None
    decimal = degrees + minutes / 60.0 + seconds / 3600.0
    ref_str = str(ref).strip().upper()
    if ref_str in ("S", "W"):
        decimal = -decimal
    return decimal


def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, Fraction):
        return float(value)
    if hasattr(value, "numerator") and hasattr(value, "denominator"):
        denom = value.denominator
        if denom == 0:
            return None
        return float(value.numerator) / float(denom)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
