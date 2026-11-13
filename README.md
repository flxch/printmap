# Print Map

Creation of true-to-scale topographic maps or satellite photos from
web-based map tiles.  The maps or photos can either be output as PDF,
JPG, or PNG.  For viewing the topographic maps online in a browser,
visit the web page [OpenTopoMap.org](https://opentopomap.org).  For
license issues, see https://opentopomap.org/about (for topographic
maps) and
https://doc.esri.com/en/arcgis-online/latest/reference/static-maps.html
(for satellite photos), respectively.

## Usage

`printmap.py` is a small Python program.  It requires the libraries
`mercantile`, `img2pdf`, `tqdm`, ... , which can be installed by `pip
install <LIBRARY>`.

The command-line flags of `printmap.puy` are as follows (see also
`./printmap.py -h`):

- **`--lat`** and **`--lon`**: Latitude and longitude of the map's center
  point.  Both flags are mandatory.
- **`--scale`** (default: `25000`): The map's scale, such as 1:5000 for
  higher detail or 1:25000 for a broader view.
- **`--zoom`** (default: `15`): Defines the tile zoom level for the
  map. Maximum zoom levels are generally 17 for topographic maps and
  ~19 for satellite imagery, depending on location.
- **`--provider`** (default: `topographic`): Select the map tile
  provider. Options include `topographic` (OpenTopoMap) or `satellite`
  (Esri Satellite). 
- **`--format`** (default: `A4`): Paper format (DIN standard),
  A0, A1, A2, A3, A4.
- **`--orientation`** (default: `landscape`): Choose between portrait or
  landscape orientation for the map.  
- **`--label`**: Optional text annotation added to the map (e.g.,
  "City Map") in a box at the bottom left corner. If the provided text
  is the empty string, the box only contains the scale, the
  coordinates, and a copyright statement for the map data.  If
  omitted, no box and no text is added.
- **`--output`** (or **`-o`**): Name of the output file. If omitted, a
  name is auto-generated based on the provider, scale, and paper
  orientation.  The output format is PDF (default), JPG, or PNG,
  determined by the file name's suffix.
- **`--quiet`** (or **`-q`**): Suppress output.

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

# Map Legend

The topographic maps refer to standard topographic map legend
guides. You can find helpful references and examples in the `legend`
subdirectory of this project. These resources explain common symbols
like contour lines, landmarks, vegetation, and water bodies.

For additional information:
- [OpenTopoMap Legend](https://opentopomap.org/about#legend)
- [Official USGS Topo Map
  Symbols](https://pubs.usgs.gov/gip/TopographicMapSymbols/topomapsymbols.pdf)

## Notes

* On the web page [OpenTopoMap.org](https://opentopomap.org/) one can
  look at the topographical map prior to downloading the data and
  creating the map, e.g., as PDF.  One can also read from the web page
  the aptitude and longitude of the paper center.  They are provided
  in the URL of the shown map.  For vector graphics, use this
  [link](https://opentopomap.org/vector).  It is a bit nicer and more
  detailed.  But it is also slower in a web browser because the map
  must be rendered first.  Unfortunately, the vector data cannot be
  easily downloaded.
* A higher zoom level provides more details and more tiles that must
  be downloaded from the map server.  Choose the zoom level wisely to
  reduce internet traffic.  (The zoom level is also provided by the
  URL, when looking at a map in the browser.)  Zoom level 17 is the
  maximum for topographic maps.  For satellite photos, the maximum is
  around 19.  The actual value depends on the area.  Not sure what the
  minimums are, maybe 0 or 1.

# Todos

1. Check command-line arguments, i.e., are the provided values valid.
2. Improve error handling.
3. Restructure code: promote modularity and readability. Avoid large,
   monolithic functions to simplify maintenance and testing.

