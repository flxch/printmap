# Print Map

Creation of true-to-scale topographic maps or satellite photos from
web-based map tiles.  The maps or photos can either be output as PDF, JPG, or
PNG.  For viewing the topographic maps online in a browser, visit the
web page https://opentopomap.org

## Usage

The program's command-line flags are as follows:

- `--provider` (default: `topographic`): Select the map tile
  provider. Options include `topographic` (OpenTopoMap) or `satellite`
  (Esri Satellite).
- `--lat` and `--lon` (default: `47.073093` and `15.443709`): Latitude
  and longitude of the map's center point.
- `--scale` (default: `25000`): The map's scale, such as 1:5000 for
  higher detail or 1:25000 for a broader view.
- `--format` (default: `A4`): Paper format (DIN standard),
  A0, A1, A2, A3, A4.
- `--orientation` (default: `landscape`): Choose between portrait or
  landscape orientation for the map.
- `--zoom` (default: `15`): Defines the tile zoom level for the
  map. Maximum zoom levels are generally 17 for topographic maps and
  ~19 for satellite imagery, depending on location.
- `--output-format` (default: `pdf`): The output file format,
  including options for `pdf`, `jpeg`, or `png`.
- `--label`: Optional text annotation added to the map (e.g., "City
  Map"). If omitted, no annotation is added. If the provided text is
  an empty string, the annotation defaults to the scale, coordinates,
  and copyright statement for the map data.
- `--output` (or `-o`): Name of the output file. If omitted, a name is
  auto-generated based on the provider, scale, and format.

## Examples

* City of Graz, Austria.
  Topographic city map with scale 1:10000 on DIN A0 paper in
  landscape:
```
./printmap.py --lat 47.05412 --lon 15.44316 \
              --scale 10000 --zoom 16 --format a0 \
              --label "Graz, Austria" \
              --output examples/graz_16_10000_landscape.pdf
```
  - View the map in a browser:
    https://opentopomap.org/vector/#16/47.05412/15.44316
  - Create a satellite photo of the same area: `./printmap.py --provider satellite --lat 47.05412 --lon 15.44316 --scale 10000 --zoom 16 --format a0 --label "Graz, Austria" --output examples/graz_16_10000_landscape_satellite.pdf`

* Palermo Beach, Albania.
  Topographic map with scale 1:5000 on DIN A0 paper in landscape:
```
./printmap.py --lat 40.06301 --lon 19.79264 \
              --scale 5000 --zoom 16 --format a0 \
              --label "Palermo Beach, Albania" \
              --output examples/palermobeach_16_5000_landscape.pdf
```
  - View the map in a browser: 
    https://opentopomap.org/vector/#16/40.06301/19.79264
  - Create a satellite photo of the same area: `./printmap.py --provider satellite --lat 40.06301 --lon 19.79264 --scale 5000 --zoom 16 --format a0 --label "Palermo Beach, Albania" --output examples/palermobeach_16_5000_landscape_satellite.pdf`

## Notes

* For license issues of the tiles, which are downloaded from the
  internet, see https://opentopomap.org/about and
  https://doc.esri.com/en/arcgis-online/latest/reference/static-maps.html
  respectively.  Note that with the --label flag, a small box on the
  left bottom with copyright statement can be added to the output
  file.
* On the web pages https://opentopomap.org/ and
  https://opentopomap.org/vector (vector graphics) one can look at the
  topographical maps prior to downloading the data and creating the
  PDF.  One can also read from those web pages the aptitude and
  longitude of the paper center.  The vector graphics is a bit nicer
  and detailed.  Unfortunately, the vector data cannot be easily
  downloaded.  It is also slower in a web browser because it must
  be rendered.
* The following Python libraries must be installed: `mercantile`,
  `img2pdf`, `tqdm`, ...  Use `pip install ...`.
* A higher zoom factor provides more details. More tiles must be
  downloaded from the map server.
* Use the map maker sensibly and do not create unnecessary/too much
  internet traffic.
* Zoom factor 17 is the maximum for topographic maps.  For satellite
  photos, the maximum is around 19.  This can depend on the area.  Not
  sure what the minimums are?

# Map Legend

The topographic maps refer to standard topographic map legend
guides. You can find helpful references and examples in the `legend`
subdirectory of this project. These resources explain common symbols
like contour lines, landmarks, vegetation, and water bodies.

For additional information:
- [OpenTopoMap Legend](https://opentopomap.org/about#legend)
- [Official USGS Topo Map
  Symbols](https://pubs.usgs.gov/gip/TopographicMapSymbols/topomapsymbols.pdf)

# Todos

1. Improve error handling.
2. Check command-line arguments.
3. The flags `--lat` and `--lon` should not have defaults.  They
   should be mandatory input parameters.
4. Set output file format depending on the suffix of the output file.
   The output-format flag overwrites this.
5. Add quiet flag for no output on stdout.
6. Errors should be printed on stderr.
7. Restructure code: promote modularity and readability. Avoid large, monolithic functions to simplify maintenance and testing.

