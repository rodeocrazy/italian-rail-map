Italy has one of Europe's most complex rail networks. Trenitalia runs the national service. Italo competes on high-speed routes. Dozens of regional operators cover local lines. No single map shows all of it together.
 
This project fixes that.
 
**[Explore the map →](https://italian-rail-map.vercel.app)**

**[Github Repo →](https://github.com/rodeocrazy/italian-rail-map)**

---
 
## What it shows
 
3,900+ stations across Italy, sourced from OpenStreetMap and cross-referenced with Wikidata. Click any station to see which lines it sits on and which stations it connects to directly. The network includes mainline rail, regional services, narrow gauge lines, funiculars, and metro systems.
 
Station connections come from Wikidata's adjacency data (P197), which links each station to its neighbours on each line. This approach captures the actual route structure rather than inferring it from track geometry.
 
## Why it exists
 
Italy's rail network is fragmented across carriers, and no public tool maps it as a whole. Trenitalia's journey planner only shows their own services. Regional operators publish their own separate maps. Wikidata and OpenStreetMap have the underlying data but no visual layer on top of it.
 
This map pulls from both sources and puts everything in one place.
 
## Tech stack
 
- **React** + **Deck.gl** + **Mapbox GL JS** for the map and rendering
- **OpenStreetMap Overpass API** for station and track geometry data
- **Wikidata SPARQL** for station adjacency (P197) and line membership (P81)
- **SQLite** for local data processing and export
- **Vercel** for hosting
 
## Data sources
 
Station and route data comes from OpenStreetMap contributors and Wikidata editors. Both are open datasets under open licenses. If you notice a missing station or incorrect connection, the best fix is to update the source data directly on Wikidata or OSM — the map rebuilds from those sources.
 
## Running locally
 
```bash
# Install dependencies
npm install
pip install requests numpy pandas
 
# Build the database
python build_italy_rail_db.py --stations Train_station_data.json --routes Train_routes_data.json --db italy_rail.db
python import_wikidata.py --db italy_rail.db --save-json wikidata_adjacency.json
python import_wikidata_lines.py --db italy_rail.db --save-json wikidata_lines.json
python export_data.py --db italy_rail.db --out public/data
 
# Start dev server
npm run dev
```
 
You'll need a Mapbox public token in a `.env` file:
```
VITE_MAPBOX_TOKEN=your_token_here
```
 
Raw data files (the Overpass JSON exports) are not included in the repo due to size. Run the Overpass queries in `build_italy_rail_db.py` to regenerate them.
 
## Coverage

 
| Type | Count |
|------|-------|
| Stations | 3,900+ |
| Connected stations | 3,800+ |
| Station connections | 24,000+ |
| Lines | 2,200+ |
 

Coverage is strongest on the main national network and regional lines in northern and central Italy. Some smaller halts in the south and islands have incomplete adjacency data in Wikidata.