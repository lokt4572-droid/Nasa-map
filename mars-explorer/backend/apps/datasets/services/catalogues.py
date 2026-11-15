"""One entry point for elevation catalogues, dispatched by body.

MARS, MOON -> USGS Astrogeology STAC (stac_client)
EARTH      -> Copernicus DEM GLO-30 tile list on AWS Open Data (copernicus_client)
Each adapter follows its provider's own protocol; this module only routes calls."""
from __future__ import annotations

from . import copernicus_client, stac_client
from .stac_client import StacCollection, StacError, point_in_footprint  # noqa: F401 - re-exported

MAX_LIMIT = stac_client.MAX_LIMIT


def provider_name(planet: str) -> str:
    return copernicus_client.PROVIDER if planet == "EARTH" else stac_client.PROVIDER


def collections_for(planet: str, data_type: str | None = None) -> list[StacCollection]:
    if planet == "EARTH":
        return [copernicus_client.COLLECTION] if data_type in (None, "DEM") else []
    return stac_client.collections_for(planet, data_type)


def search(planet: str, bbox=None, point=None, data_type: str | None = None, max_resolution_m=None,
           collections: list[str] | None = None, limit: int = 50) -> dict:
    if planet == "EARTH":
        if data_type not in (None, "DEM") or (collections and copernicus_client.COLLECTION.id not in collections):
            return {"products": [], "matched": 0, "truncated": False, "collections": []}
        if bbox is None and point is None:
            raise ValueError("bbox or point is required")
        return copernicus_client.search(bbox=bbox, point=point, max_resolution_m=max_resolution_m, limit=limit)
    return stac_client.search(planet, bbox=bbox, point=point, data_type=data_type, max_resolution_m=max_resolution_m,
                              collections=collections, limit=limit)


def get_product(collection: str, product_id: str) -> dict:
    if collection == copernicus_client.COLLECTION.id:
        return copernicus_client.get_product(product_id)
    return stac_client.get_product(collection, product_id)
