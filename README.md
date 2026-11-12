# Make Map

Creation of true-to-scale topographic maps or satellite photos from
web tiles.  The maps or photos can either be output as PDF, JPG, or
PNG.  For viewing the topographic maps online in a browser, visit the
site https://opentopomap.org

## Usage

TODO: Explain command-line flags.

## Examples

* City of Graz, Austria.
  Topographic city map with scale 1:10000 on DIN A0 paper in
  landscape:
```
./makemap.py --lat 47.05412 --lon 15.44316 \
             --scale 10000 --zoom 16 --format a0 \
			 --output graz_16_10000-landscape.pdf
```
  - View the map in a browser:
    https://opentopomap.org/vector/#12/47.04875/15.43575
  - Create a satellite photo of the same area: `./makemap.py --provider satellite --lat 47.05412 --lon 15.44316 --scale 10000 --zoom 16 --format a0 --output sat_graz_16_10000-landscape.pdf`

* Palermo Beach, Albania.
  Topographic map with scale 1:5000 on DIN A0 paper in landscape:
```
./makemap.py --lat 40.06301 --lon 19.79264 \
             --scale 5000 --zoom 16 --format a0 
			 --output palermobeach_16_5000-landscape.pdf
```
  - View the map in a browser: 
    https://opentopomap.org/vector/#14/40.06301/19.79264
  - Create a satellite photo of the same area: `./makemap.py --provider satellite --lat 40.06301 --lon 19.79264 --scale 5000 --zoom 16 --format a0 --output sat_palermobeach_16_5000-landscape.pdf`

## Notes

* For license issues, see https://opentopomap.org/about and
  https://doc.esri.com/en/arcgis-online/latest/reference/static-maps.html#:~:text=The%20following%20attribution%20is%20recommended%20as%20a,limited%20to%2C%20commercial%20monetization%20and%20direct%20resale. 
* On web pages https://opentopomap.org/ and
  https://opentopomap.org/vector (vector graphics) one can look at the
  topographical maps prior to downloading the data and creating the
  PDF.  One can also read from those web pages the aptitude and
  longitude of the paper center.  The vector graphics is a bit nicer
  and detailed.  Unfortunately, the vector data cannot be easily
  downloaded.  It is also slower in a web browser because the it must
  be rendered.
* The following Python libraries must be installed: `mercantile`,
  `img2pdf`, ...  Use `pip install ...`.
* A higher zoom factor provides more details. More tiles must be
  downloaded from the map server.
* Use the map maker sensibly and do not create unnecessary/too much
  internet traffic.
* Zoom factor 17 is the maximum for topographic maps.  For satellite
  photos, the maximum is around 19.  This can depend on the area.  Not
  sure what the minimums are?

# Map Legend

TODO: Provide linksto the pictures depicting and explaining the
symbols in a topographic map.

# Todos

* Improve error handling.
* Check command-line arguments.
* Set output file format depending on the suffix of the output file.
* Add quiet flag.
* Progress status bar for download.
* ...

