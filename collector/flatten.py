"""Flatten nested JSON / GeoJSON properties into DB column dicts."""

from __future__ import annotations

import ast
import json
from typing import Any, Optional


def _parse_maybe_dict(value: Any) -> Optional[dict]:
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
        try:
            parsed = ast.literal_eval(value)
            if isinstance(parsed, dict):
                return parsed
        except (ValueError, SyntaxError):
            pass
    return None


def _scalar(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "item"):
        return value.item()
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _json_value(value: Any) -> Any:
    """Keep lists/dicts as JSON-serializable structures."""
    if value is None:
        return None
    if hasattr(value, "item"):
        return value.item()
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, dict)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            try:
                return ast.literal_eval(value)
            except (ValueError, SyntaxError):
                return value
    return str(value)


def flatten_data_mos_properties(props: dict) -> dict[str, Any]:
    """Map GeoJSON feature properties to data_mos.items columns."""
    attrs = _parse_maybe_dict(props.get("attributes")) or {}

    def a(key: str) -> Any:
        return _scalar(attrs.get(key))

    def aj(key: str) -> Any:
        return _json_value(attrs.get(key))

    return {
        "dataset_id": _scalar(props.get("datasetId")),
        "row_id": _scalar(props.get("rowId")),
        "version_number": _scalar(props.get("versionNumber")),
        "release_number": _scalar(props.get("releaseNumber")),
        "order_number": a("OrderNumber"),
        "order_date": a("OrderDate"),
        "customer_construction": a("CustomerConstruction"),
        "customer_construction_inn": a("CustomerConstructionINN"),
        "general_contractor": a("GeneralContractor"),
        "general_contractor_inn": a("GeneralContractorINN"),
        "work_type": aj("WorkType"),
        "order_work": aj("OrderWork"),
        "earthwork_objectives": aj("EarthworkObjectives"),
        "objectives_temp_fences": aj("ObjectivesOfTheInstallationOfTemporaryFences"),
        "objectives_temp_objects": aj("ObjectivesOfThePlacementOfTemporaryObjects"),
        "address_nearby_building": a("AddressOfNearbyBuilding"),
        "adm_area": a("AdmArea"),
        "district": a("District"),
        "work_place_description": a("WorkPlaceDescription"),
        "work_start_date": a("WorkStartDate"),
        "work_end_date": a("WorkEndDate"),
        "global_id": a("global_id"),
    }


def flatten_genplan_payload(payload: dict, file_name: str) -> dict[str, Any]:
    """Map response_*.json to genplan.responses columns."""
    photo = _parse_maybe_dict(payload.get("photo_coordinate")) or {}
    order = _parse_maybe_dict(payload.get("order")) or {}
    yolo = _parse_maybe_dict(payload.get("yolo")) or {}

    return {
        "file_name": file_name,
        "opening": payload.get("opening"),
        "legal": payload.get("legal"),
        "description": _scalar(payload.get("description")),
        "image": _scalar(payload.get("image")),
        "photo_lat": _scalar(photo.get("lat")),
        "photo_lng": _scalar(photo.get("lng")),
        "photo_azimuth_deg": _scalar(photo.get("azimuth_deg")),
        "order_source": _scalar(order.get("source")),
        "order_doc_num": _scalar(order.get("doc_num")),
        "order_work_types": _scalar(order.get("work_types")),
        "order_date_start": _scalar(order.get("date_start")),
        "order_date_end": _scalar(order.get("date_end")),
        "order_customer": _scalar(order.get("customer")),
        "order_status": _scalar(order.get("status")),
        "yolo_label": _scalar(yolo.get("label")),
        "yolo_votes": _json_value(yolo.get("votes")),
    }


def order_coord_geojson(payload: dict) -> Optional[str]:
    order_coord = payload.get("order_coord")
    if isinstance(order_coord, dict) and order_coord.get("type") and order_coord.get("coordinates"):
        return json.dumps(order_coord)
    return None


def photo_point_geojson(payload: dict) -> Optional[str]:
    photo = _parse_maybe_dict(payload.get("photo_coordinate")) or {}
    if "lat" in photo and "lng" in photo:
        return json.dumps({
            "type": "Point",
            "coordinates": [photo["lng"], photo["lat"]],
        })
    return None
