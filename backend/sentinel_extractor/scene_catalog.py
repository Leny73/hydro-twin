from __future__ import annotations

from pathlib import Path
from datetime import datetime
import json
from shapely.geometry import box, mapping

import pandas as pd
from pystac_client import Client

BASE = Path(".")  
DATA = BASE / "data"
RAW = DATA / "raw"
TABLES = DATA / "tables"

for p in [RAW, TABLES]:
    p.mkdir(parents=True, exist_ok=True)

print("DATA:", DATA.resolve())
print("TABLES:", TABLES.resolve())

STAC_URL = "https://stac.dataspace.copernicus.eu/v1/"


S1_COLLECTION = "sentinel-1-grd"
S2_COLLECTION = "sentinel-2-l2a"

MAX_ITEMS = 100
S2_CLOUD_MAX = 20


client = Client.open(STAC_URL)





DATE_START = "2023-10-01"
DATE_END   = "2025-04-01"


cloud_cover_max=20
MAX_ITEMS=50

def scene_catalog(
        collection: str, 
        bbox: list, 
        start_date: str, 
        end_date: str
    ) -> list:
    
    bbox_geom=mapping(box(*bbox))

    query = None
    if cloud_cover_max is not None:
        query = {"eo:cloud_cover": {"lt": cloud_cover_max}}

    search = client.search(
        collections=[collection],
        intersects=bbox_geom,
        query=query,
        max_items=MAX_ITEMS,
        limit=50,
    )

    items=search.get_items()

    rows = []

    for item in search.get_items():
        props = item.properties or {}

        rows.append({
            "id": item.id,
            "datetime": props.get("datetime"),
            "start_datetime": props.get("start_datetime"),
            "end_datetime": props.get("end_datetime"),
            "eo:cloud_cover": props.get("eo:cloud_cover"),
            "sat:orbit_state": props.get("sat:orbit_state"),
            "sat:relative_orbit": props.get("sat:relative_orbit"),
            "platform": props.get("platform"),
            "instruments": props.get("instruments"),
        })

    df = pd.DataFrame(rows)

    if not df.empty and "datetime" in df.columns:
        df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce", utc=True)
        df = df.sort_values("datetime").reset_index(drop=True)

    return df


if __name__=="__main__":
    df = scene_catalog(
        collection=S2_COLLECTION,
        bbox=[8.0, 42.0, 30.0, 52.0],
        start_date=DATE_START,
        end_date=DATE_END
    )
    import pdb
    pdb.set_trace()