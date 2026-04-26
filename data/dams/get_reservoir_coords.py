import urllib.request, json

# Query for the reservoir water bodies (язовир = reservoir in Bulgarian)
# These are "natural=water" with "water=reservoir" or just the named water bodies
query = b'[out:json];(relation["natural"="water"]["name"~"Kardzhal|Studen|Ivailovgrad",i];relation["landuse"="reservoir"][bbox:41.4,25.2,41.8,26.3];way["natural"="water"][bbox:41.4,25.2,41.8,26.3]["name"~"Kardzhal|Studen|Ivailovgrad",i];);out center;'

req = urllib.request.Request(
    'https://overpass-api.de/api/interpreter',
    data=query,
    method='POST'
)
try:
    with urllib.request.urlopen(req, timeout=20) as r:
        d = json.loads(r.read())
    for e in d.get('elements', []):
        name   = e.get('tags', {}).get('name', 'unnamed')
        center = e.get('center', {})
        lat    = center.get('lat', e.get('lat', '?'))
        lon    = center.get('lon', e.get('lon', '?'))
        print(f"{e['type']:8} id={e['id']} | {name:40} | lat={lat} lon={lon}")
    print(f"Total: {len(d.get('elements',[]))} elements")
except Exception as ex:
    print('Error:', ex)
