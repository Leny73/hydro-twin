# data_science/

> **Owner: Data Analytics & Meteorology Team**

This directory is fully isolated from the AWS infrastructure. The only integration
point is the function signature in `../backend/sentinel_extractor.py`.

---

## Directory Structure

```
data_science/
├── notebooks/          Jupyter notebooks for EDA and rapid prototyping
└── models/             Serialised model artefacts (pickle, ONNX, joblib)
```

---

## Integration Contract

`lambda_handler.py` imports one function from the backend stub:

```python
from sentinel_extractor import get_eo_and_weather_data

result = get_eo_and_weather_data(bbox=[lon_min, lat_min, lon_max, lat_max])
```

The function **must** return a `dict` with these exact keys (see the docstring
in `sentinel_extractor.py` for units and descriptions):

| Key | Type | Description |
|-----|------|-------------|
| `ndvi` | float | Normalised Difference Vegetation Index |
| `soil_moisture_pct` | float | Volumetric soil moisture % |
| `precip_mm_7d` | float | Total precipitation last 7 days (mm) |
| `precip_mm_30d` | float | Total precipitation last 30 days (mm) |
| `river_level_m` | float | River / reservoir level above datum (m) |
| `flood_extent_km2` | float | SAR-derived flood extent (km²) |
| `temp_max_c` | float | Max air temperature last 7 days (°C) |
| `drought_index` | float | SPI-3 or PDSI index |
| `data_timestamp` | str | ISO-8601 UTC timestamp |
| `source` | str | Dataset note / data quality warning |

**Do not rename or remove keys.** Add extra keys freely — the Bedrock prompt
will pick them up automatically.

---

## Recommended Data Sources

| Source | What it provides | Access |
|--------|-----------------|--------|
| [Copernicus Data Space Ecosystem](https://dataspace.copernicus.eu/) | Sentinel-1, -2, -3 imagery | Free (EU login) |
| [Sentinel Hub](https://www.sentinel-hub.com/) | Process API for NDVI, SAR | Free trial |
| [OpenMeteo](https://open-meteo.com/) | Precipitation, temperature forecasts | Free, no key |
| [ECMWF ERA5 (CDS)](https://cds.climate.copernicus.eu/) | Reanalysis climatology | Free (CDS login) |
| [Global Flood Database](https://global-flood-database.cloudtostreet.ai/) | Historical flood masks | Free research |

---

## Getting Started

```bash
# Create a virtual environment (Python 3.10+)
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

# Install analysis dependencies
pip install jupyterlab sentinelhub openmeteo-requests pandas numpy rasterio

# Launch Jupyter
jupyter lab notebooks/
```

---

## Tasks

- [ ] Implement `sentinel_extractor.py` — replace dummy dict with real API calls
- [ ] Validate meteorology thresholds in `meteorology_rules.md` with historical data
- [ ] Add unit tests: `tests/test_sentinel_extractor.py`
- [ ] Add a data-freshness guard (reject observations > 24 h old)
- [ ] Document regional climatological baselines (WMO 1991–2020 normals)
