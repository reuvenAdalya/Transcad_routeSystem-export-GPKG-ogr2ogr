# TransCAD route system → GeoPackage (no TransCAD needed)

[עברית](README.he.md)

`transcad_export.py` reads TransCAD's binary files directly and builds a WGS84 GeoPackage with four layers:

| Layer | Content |
|---|---|
| `routes` | Bus routes, with every field of the route table |
| `route_stops` | Stops per route: each stop assigned to its route and street link, in order (see below) |
| `stops_physical` | Physical stops |
| `streets` | The street network |

## Which files it supports
Only a TransCAD bus route system folder laid out like this. The names must match exactly:

- `Streets.dbd`, with `Streets.dln`, `Streets.pts`, `Streets.BIN` and `Streets.DCB`
- `Bus Routes.rts` and `Bus Routes.rtg`
- `Bus RoutesR.bin` + `.DCB`: the route table
- `Bus RoutesP.bin` + `.DCB`: physical stops, with `LongitudeN`/`LatitudeN` fields
- `Bus RoutesS.r0` and `Bus RoutesS.bin` + `.DCB`: stops per route

It does not handle other point or polygon layers, matrices (`.mtx`), or networks outside Israel.

## Requirements
1. **Python 3**, from python.org or any existing install.
2. **numpy**, the only third-party library. Everything else is in the standard library.
   ```
   python -m pip install numpy
   ```
3. **QGIS**, for the `ogr2ogr.exe` it ships with. The script finds it on its own: first on PATH, then in the newest QGIS install under `Program Files`. If it isn't found, pass the full path to `ogr2ogr.exe` as the third argument.

## Usage
```
python transcad_export.py "<input_folder>" "<output_folder>" ["<path\to\ogr2ogr.exe>"]
```
For example:
```
python transcad_export.py "C:\data\transcad_input" "C:\data\output"
```
A run takes a few minutes and needs about 800 MB free in the output folder.

## Output
- `RS_corrected_WGS84.gpkg`: **the file to use.** Its coordinates are corrected.
- `routes.csv`, `route_stops.csv`, `stops_physical.csv`, `streets.csv`: intermediate files with a WKT column, in TransCAD's raw coordinates, **before** the datum correction. Do not load them as WGS84.

## Good to know
- **Datum correction:** TransCAD stores coordinates in the Israel 1993 datum, not WGS84. Without correction everything is off by about 78 m. The script corrects this automatically, on the same principle as [israel_trancsad_fix](https://github.com/eithanwes/israel_trancsad_fix).
- **`geom_status` field in the routes layer:**
  - `complete`: the route is whole.
  - `filled_from_streets`: gaps were filled with the shortest path over the streets, ignoring one-way restrictions. Worth checking by eye.
  - `partial`: gaps remain, and the route is broken.
- **`route_stops` layer:** each record is one stop of one route. Main fields:
  - `ROUTE_ID`: the route. Joins to `Route_ID` in `routes`.
  - `SEQ`: the stop's position along the route.
  - `MILEPOST`: distance from the start of the route, in km.
  - `DIST_TO_NEXT`: distance to the next stop, in km. Empty on the last stop.
  - `LINK_ID`: the street link the stop sits on. Joins to `ID` in `streets`.
  - `PHYSICAL_STOP_ID`: the physical stop. Joins to `STOP_ID` in `stops_physical`.
  - `PASS_COUNT`: how many times the route passes the stop.
  - The `route_*` fields are route details; the other fields (name, address, `StopActivity` and more) come from the stop table.

  `ROUTE_ID`, `MILEPOST`, `PASS_COUNT` and `PHYSICAL_STOP_ID` were checked against a shapefile exported by TransCAD itself and matched 100%.
- **The format was reverse-engineered.** Another TransCAD version may break the script. After each run, check the messages it prints: link count, route count, and the breakdown of routes by completeness.

## License
GPL-3.0. See [LICENSE](LICENSE).
