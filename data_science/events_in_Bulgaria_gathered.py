#!/usr/bin/env python
from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DATA_SCIENCE = ROOT / "data_science"


def script_path(filename: str) -> str:
    path = DATA_SCIENCE / filename
    if not path.exists():
        raise FileNotFoundError(f"Missing script: {path}")
    return str(path)


def run(cmd: list[str]) -> None:
    print("\nRUN:", " ".join(cmd))
    subprocess.run(cmd, check=True)


def period_last_years_desc(years_back: int, end_offset_days: int) -> tuple[str, str]:
    end = date.today() - timedelta(days=end_offset_days)
    start = end - timedelta(days=365 * years_back)
    return start.isoformat(), end.isoformat()


def make_descending_chunks(start: str, end: str, chunk_days: int) -> list[tuple[str, str]]:
    start_d = pd.to_datetime(start).date()
    end_d = pd.to_datetime(end).date()

    chunks = []
    cur_end = end_d

    while cur_end >= start_d:
        cur_start = max(start_d, cur_end - timedelta(days=chunk_days - 1))
        chunks.append((cur_start.isoformat(), cur_end.isoformat()))
        cur_end = cur_start - timedelta(days=1)

    return chunks


def append_row(row: dict, path: str) -> None:
    out = ROOT / path
    out.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([row]).to_csv(out, mode="a", header=not out.exists(), index=False)


def summarize_existing(hazard_csv: str, out_summary: str) -> pd.DataFrame:
    path = ROOT / hazard_csv
    if not path.exists():
        return pd.DataFrame()

    df = pd.read_csv(path)
    if df.empty or "target_date" not in df.columns:
        return pd.DataFrame()

    df["target_date"] = pd.to_datetime(df["target_date"], errors="coerce")
    df = df.dropna(subset=["target_date"])

    for col in ["flood_event", "drought_event"]:
        if col not in df.columns:
            df[col] = 0
        df[col] = df[col].fillna(0).astype(int)

    df["compound_event"] = ((df["flood_event"] == 1) & (df["drought_event"] == 1)).astype(int)
    df["any_hazard_event"] = ((df["flood_event"] == 1) | (df["drought_event"] == 1)).astype(int)

    summary = (
        df.groupby("aoi_name", as_index=False)
        .agg(
            historic_start=("target_date", "min"),
            historic_end=("target_date", "max"),
            checkpoints=("target_date", "count"),
            flood_events=("flood_event", "sum"),
            drought_events=("drought_event", "sum"),
            compound_events=("compound_event", "sum"),
            any_hazard_events=("any_hazard_event", "sum"),
            max_flood_area_km2=("gfm_flooded_area_km2", "max"),
            max_flood_fraction=("gfm_flood_fraction", "max"),
            max_cdi=("cdi_max", "max"),
            mean_cdi=("cdi_mean", "mean"),
        )
    )

    out = ROOT / out_summary
    out.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(out, index=False)
    return summary


def print_reference_statement(summary: pd.DataFrame) -> None:
    if summary.empty:
        print("No historic hazard reference data yet.")
        return

    global_start = pd.to_datetime(summary["historic_start"]).min().date()
    global_end = pd.to_datetime(summary["historic_end"]).max().date()

    print("\nHistoric reference status")
    print("─────────────────────────")
    print(f"We have historic hazard data from {global_start} up to {global_end}.")
    print(f"Referenced flood checkpoints:   {int(summary['flood_events'].sum())}")
    print(f"Referenced drought checkpoints: {int(summary['drought_events'].sum())}")
    print(f"Compound checkpoints:           {int(summary['compound_events'].sum())}")
    print("\nBy AOI:")
    print(summary.to_string(index=False))


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument("--aois", default="data/aois_bulgaria.json")
    parser.add_argument("--years-back", type=int, default=2)
    parser.add_argument("--end-offset-days", type=int, default=2)

    parser.add_argument("--chunk-days", type=int, default=30)
    parser.add_argument("--flood-window-days", type=int, default=6)
    parser.add_argument("--flood-step-days", type=int, default=3)
    parser.add_argument("--drought-day", type=int, default=1)

    parser.add_argument("--skip-download", action="store_true")

    parser.add_argument("--flood-script", default="collect_flood_labels_gfm_stac.py")
    parser.add_argument("--drought-script", default="drought_label_extractor.py")
    parser.add_argument("--timeseries-script", default="build_hazard_event_timeseries.py")

    parser.add_argument("--flood-out", default="data/labels/flood_gfm_bulgaria_2y.csv")
    parser.add_argument("--drought-out", default="data/labels/drought_edo_bulgaria_2y.csv")
    parser.add_argument("--hazard-out", default="data/labels/hazard_event_timeseries_bulgaria_2y.csv")
    parser.add_argument("--summary-out", default="data/labels/hazard_reference_summary_bulgaria_2y.csv")
    parser.add_argument("--chunk-log", default="data/labels/hazard_reference_chunk_log.csv")

    args = parser.parse_args()

    flood_script = script_path(args.flood_script)
    drought_script = script_path(args.drought_script)
    timeseries_script = script_path(args.timeseries_script)

    start, end = period_last_years_desc(args.years_back, args.end_offset_days)
    chunks = make_descending_chunks(start, end, args.chunk_days)

    print("Historic hazard reference builder")
    print("─────────────────────────────────")
    print(f"Overall period: {start} → {end}")
    print("Direction: newest → oldest")
    print(f"Flood config: {args.flood_window_days}d window / {args.flood_step_days}d step")
    print(f"Drought config: monthly CDI, day {args.drought_day}")
    print(f"Chunks: {len(chunks)} × ~{args.chunk_days} days")

    for chunk_start, chunk_end in chunks:
        print(f"\nProcessing chunk: {chunk_start} → {chunk_end}")

        try:
            if not args.skip_download:
                run([
                    sys.executable,
                    flood_script,
                    "--aois", args.aois,
                    "--start", chunk_start,
                    "--end", chunk_end,
                    "--window-days", str(args.flood_window_days),
                    "--step-days", str(args.flood_step_days),
                    "--out", args.flood_out,
                    "--resume",
                ])

                run([
                    sys.executable,
                    drought_script,
                    "--aois", args.aois,
                    "--start", chunk_start,
                    "--end", chunk_end,
                    "--day", str(args.drought_day),
                    "--out", args.drought_out,
                    "--resume",
                ])

            run([
                sys.executable,
                timeseries_script,
                "--flood", args.flood_out,
                "--drought", args.drought_out,
                "--out", args.hazard_out,
            ])

            summary = summarize_existing(args.hazard_out, args.summary_out)

            append_row({
                "chunk_start": chunk_start,
                "chunk_end": chunk_end,
                "status": "completed",
                "historic_start_available": (
                    pd.to_datetime(summary["historic_start"]).min().date()
                    if not summary.empty else None
                ),
                "historic_end_available": (
                    pd.to_datetime(summary["historic_end"]).max().date()
                    if not summary.empty else None
                ),
                "flood_events": int(summary["flood_events"].sum()) if not summary.empty else 0,
                "drought_events": int(summary["drought_events"].sum()) if not summary.empty else 0,
                "compound_events": int(summary["compound_events"].sum()) if not summary.empty else 0,
            }, args.chunk_log)

            print_reference_statement(summary)

        except KeyboardInterrupt:
            print("\nStopped by user.")
            summary = summarize_existing(args.hazard_out, args.summary_out)
            print_reference_statement(summary)
            break

        except Exception as exc:
            print(f"Chunk failed: {chunk_start} → {chunk_end}: {exc}")
            append_row({
                "chunk_start": chunk_start,
                "chunk_end": chunk_end,
                "status": "failed",
                "error": str(exc),
            }, args.chunk_log)
            continue


if __name__ == "__main__":
    main()