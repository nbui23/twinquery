# PostGIS Query Notes

## Geometry Columns

TwinQuery stores building footprints as `geom geometry(MultiPolygon, 4326)` and
map centroids as `centroid geometry(Point, 4326)`. Polygon geometry is useful
for display, while centroids are often simpler for distance filters and ranking.

## Map-Friendly SQL

Map responses should include the building identifier, descriptive fields, useful
metrics, and `ST_AsGeoJSON(geom) AS geometry_json`. The GeoJSON value lets the
API convert query rows into a FeatureCollection that Streamlit and PyDeck can
render directly.

## Distance Queries

For local screening, distance queries can cast centroids to geography:
`ST_DWithin(centroid::geography, reference_point::geography, radius_m)`. This is
appropriate for portfolio triage, but it is not a substitute for engineering or
survey-grade spatial analysis.

## Safety

Generated spatial SQL should stay read-only, use explicit columns, include
reasonable limits, and avoid full-city geometry exports unless the user has
asked for a bounded sample.
