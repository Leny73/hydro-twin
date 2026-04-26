import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dams_handler import _load_all_xls, _compute_thresholds, get_dam_statuses

series = _load_all_xls()
for name, pts in series.items():
    fills = [p['fill_pct'] for p in pts]
    thresh = _compute_thresholds(fills)
    print(f"{name}: {len(pts)} points | fill {min(fills):.1f}%-{max(fills):.1f}% | low={thresh['low']} high={thresh['high']}")

print()
result = get_dam_statuses(notify=False)
for d in result['dams']:
    print(f"{d['name']}: fill={d['fill_pct']}% alert={d['alert_level']} ndwi={d['ndwi']}")
    print(f"  reason: {d['alert_reason'][:80]}")
    print(f"  series points: {len(d['series'])}")
