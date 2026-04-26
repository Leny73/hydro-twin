#!/usr/bin/env python
"""
build_hazard_event_timeseries.py

Build unified flood + drought event time series from:
- data/labels/flood_gfm_stac_labels.csv
- data/labels/drought_edo_cdi_labels.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def load_flood_labels(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)

    df["target_date"] = pd.to_datetime(df["target_date"], errors="coerce").dt.date

    keep = [
        "aoi_name",
        "target_date",
        "gfm_flooded_area_km2",
        "gfm_flood_fraction",
        "flood_detected",
        "flood_label_binary",
        "flood_label_3tier",
    ]

    df = df[[c for c in keep if c in df.columns]].copy()

    df = df.rename(columns={
        "flood_detected": "flood_event",
    })

    if "flood_event" not in df.columns:
        df["flood_event"] = df["flood_label_binary"]

    return df


def load_drought_labels(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)

    if "target_date" in df.columns:
        df["target_date"] = pd.to_datetime(df["target_date"], errors="coerce").dt.date
    else:
        df["target_date"] = pd.to_datetime(df["date"], errors="coerce").dt.date

    keep = [
        "aoi_name",
        "target_date",
        "cdi_majority",
        "cdi_max",
        "cdi_mean",
        "selected_cdi_value",
        "drought_detected",
        "drought_label_binary",
        "drought_label_3tier",
    ]

    df = df[[c for c in keep if c in df.columns]].copy()

    if "drought_detected" not in df.columns:
        df["drought_detected"] = df["drought_label_binary"]

    df = df.rename(columns={
        "drought_detected": "drought_event",
    })

    return df


def build_event_timeseries(
    flood_csv: str,
    drought_csv: str,
    out_csv: str,
) -> pd.DataFrame:
    flood = load_flood_labels(flood_csv)
    drought = load_drought_labels(drought_csv)

    df = pd.merge(
        flood,
        drought,
        on=["aoi_name", "target_date"],
        how="outer",
    )

    df = df.sort_values(["aoi_name", "target_date"]).reset_index(drop=True)

    # Fill missing event labels
    df["flood_event"] = df["flood_event"].fillna(0).astype(int)
    df["drought_event"] = df["drought_event"].fillna(0).astype(int)

    df["flood_label_binary"] = df.get("flood_label_binary", 0)
    df["drought_label_binary"] = df.get("drought_label_binary", 0)

    df["flood_label_binary"] = df["flood_label_binary"].fillna(0).astype(int)
    df["drought_label_binary"] = df["drought_label_binary"].fillna(0).astype(int)

    if "flood_label_3tier" in df.columns:
        df["flood_label_3tier"] = df["flood_label_3tier"].fillna(0).astype(int)

    if "drought_label_3tier" in df.columns:
        df["drought_label_3tier"] = df["drought_label_3tier"].fillna(0).astype(int)

    # Combined hazard status
    def status(row):
        flood = row["flood_event"]
        drought = row["drought_event"]

        if flood and drought:
            return "COMPOUND_FLOOD_DROUGHT"
        if flood:
            return "FLOOD_EVENT"
        if drought:
            return "DROUGHT_EVENT"
        return "NO_EVENT"

    df["hazard_status"] = df.apply(status, axis=1)

    # Useful numeric target
    # 0 = no event
    # 1 = drought only
    # 2 = flood only
    # 3 = compound
    df["hazard_label_multiclass"] = df["hazard_status"].map({
        "NO_EVENT": 0,
        "DROUGHT_EVENT": 1,
        "FLOOD_EVENT": 2,
        "COMPOUND_FLOOD_DROUGHT": 3,
    }).astype(int)

    Path(out_csv).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_csv, index=False)

    return df


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--flood",
        default="data/labels/flood_gfm_stac_labels.csv",
    )
    parser.add_argument(
        "--drought",
        default="data/labels/drought_edo_cdi_labels.csv",
    )
    parser.add_argument(
        "--out",
        default="data/labels/hazard_event_timeseries.csv",
    )

    args = parser.parse_args()

    df = build_event_timeseries(
        flood_csv=args.flood,
        drought_csv=args.drought,
        out_csv=args.out,
    )

    print(f"Saved {len(df)} rows → {args.out}")
    print(df["hazard_status"].value_counts())


if __name__ == "__main__":
    main()