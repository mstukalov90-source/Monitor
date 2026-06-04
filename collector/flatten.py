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
