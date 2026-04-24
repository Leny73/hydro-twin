"""
sentinel_extractor.py — Earth Observation & Weather Data Stub
=============================================================

⚠️  THIS FILE IS OWNED BY THE DATA ANALYSTS TEAM.
    The function signature and return-dict schema MUST remain unchanged.
    lambda_handler.py imports this directly.

Responsibility:
    Retrieve Copernicus Sentinel EO data + live weather metrics for a
    given geographic bounding box and return a normalised sensor dict
    that is injected verbatim into the Bedrock (Claude 3) prompt.

Suggested data sources:
    - Copernicus Data Space Ecosystem  https://dataspace.copernicus.eu/
    - Sentinel Hub Python client       https://sentinelhub-py.readthedocs.io/
    - Sentinel-1 SAR                   → flood inundation mapping
    - Sentinel-2 NDVI / NDWI           → vegetation stress, water extent
    - Sentinel-3 OLCI / SRAL           → water level estimation
    - OpenMeteo (free, no API key)     https://open-meteo.com/
    - ECMWF ERA5 reanalysis            → precipitation climatology

TODO for Data Analysts:
    1. Replace the DUMMY dict below with real API calls.
    2. Handle missing / partial data gracefully (use None / NaN and
       add a note in the "source" field).
    3. Add a data-freshness check — refuse stale data > 24 h old.
    4. Write unit tests in /data_science/tests/test_sentinel_extractor.py
"""


def get_eo_and_weather_data(bbox: list) -> dict:
    """
    Retrieve Earth Observation and weather data for the given bounding box.

    Args:
        bbox (list): [lon_min, lat_min, lon_max, lat_max]
                     Example: [8.0, 42.0, 30.0, 52.0] for the Danube basin.

    Returns:
        dict — The following keys are REQUIRED by lambda_handler.py.
               Do NOT rename or remove keys; add extra keys as needed.

        {
            "ndvi"               (float) : Normalised Difference Vegetation Index
                                           Range −1 to 1. Healthy vegetation ≈ 0.4–0.9.
                                           Source: Sentinel-2 Band 4 / Band 8

            "soil_moisture_pct"  (float) : Volumetric soil moisture in percent (0–100).
                                           Source: Sentinel-1 SAR backscatter or ESA CCI

            "precip_mm_7d"       (float) : Total liquid precipitation over last 7 days (mm).
                                           Source: OpenMeteo / ERA5

            "precip_mm_30d"      (float) : Total precipitation over last 30 days (mm).
                                           Source: OpenMeteo / ERA5

            "river_level_m"      (float) : Observed river or reservoir level above datum (m).
                                           Source: Sentinel-3 SRAL altimetry or in-situ gauge

            "flood_extent_km2"   (float) : SAR-derived open-water flood extent (km²).
                                           0.0 when no flooding detected.
                                           Source: Sentinel-1 GRD + flood mapping algo

            "temp_max_c"         (float) : Maximum air temperature over last 7 days (°C).
                                           Source: OpenMeteo

            "drought_index"      (float) : Standardised Precipitation Index (SPI-3) or PDSI.
                                           < −1.0 = moderate drought, < −2.0 = severe drought.
                                           Source: ERA5 + SPI algorithm

            "data_timestamp"     (str)   : ISO-8601 UTC timestamp of the observation window end.
                                           Example: "2026-04-25T12:00:00Z"

            "source"             (str)   : Human-readable note on which datasets were used
                                           or any data quality warnings.
        }
    """

    # ── ⚠️  DUMMY DATA — analysts must replace this with real API calls ──────
    _ = bbox  # suppress unused-variable warning until bbox is actually used

    return {
        "ndvi":              0.42,
        "soil_moisture_pct": 28.5,
        "precip_mm_7d":      12.0,
        "precip_mm_30d":     45.0,
        "river_level_m":     3.2,
        "flood_extent_km2":  0.0,
        "temp_max_c":        24.1,
        "drought_index":     -0.3,
        "data_timestamp":    "2026-04-25T00:00:00Z",
        "source":            "DUMMY — replace with Copernicus + OpenMeteo API calls",
    }
