#!/usr/bin/python3

import argparse
from dataclasses import dataclass
import io
import math
import os
from pathlib import Path
import sys
import tempfile
import time
from typing import Any, Tuple, List

import img2pdf
import mercantile
from PIL import Image, ImageDraw, ImageFont
import requests
from tqdm import tqdm


# Disable Pillow's decompression bomb limit for large stitched maps.
# The default value is roughly 89.4 million. This can be too small for
# detailed large maps. Image.MAX_IMAGE_PIXELS = 200_000_000 might suffice
# for most cases but disable it here completely.
Image.MAX_IMAGE_PIXELS = None

# Maximum number of retries for downloading a single map tile.
MAX_TILE_DOWNLOAD_RETRIES = 3
# Pause (in seconds) between retries.
TILE_DOWNLOAD_RETRY_DELAY = 2  

# Paper formats (width, height) in millimeters for portrait orientation.
DIN_FORMATS_MM = {
    "A0": (841, 1189),
    "A1": (594, 841),
    "A2": (420, 594),
    "A3": (297, 420),
    "A4": (210, 297),
}

# Map Tile Providers configuration
PROVIDERS = {
    "topographic": {
        "site": "https://a.tile.opentopomap.org",
        "url": "https://a.tile.opentopomap.org/{z}/{x}/{y}.png",
        "user_agent": "PrivatesKartenProjekt/1.0 (kontakt@beispiel.at)",
        "is_y_inverted": False,
        "copyright": "Map Data: © OpenStreetMap Contributors, SRTM\n"
                     "Map Style: © OpenTopoMap (CC-BY-SA)"
    },
    "satellite": {
        "site": "https://server.arcgisonline.com",
        "url": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        "user_agent": "PrivateSatelliteMapProject/1.0 (kontakt@beispiel.at)",
        "is_y_inverted": True,
        "copyright": "Map image is the intellectual property of Esri and "
                     "is used herein under license.\n© 2026 Esri and its "
                     "licensors. All rights reserved."
    }
}


class MapGenError(Exception):
    """Custom exception for map generation errors to decouple logic from sys.exit."""
    pass


@dataclass
class Size:
    """
    Represents a (width, height) pair, in mm, m, or pixels.
    """
    width: float
    height: float

    
@dataclass
class Bounds:
    """
    Represents a rectangle by min/max coordinates (x/y or lon/lat or meters).
    """
    min_x: float
    max_x: float
    min_y: float
    max_y: float

    @property
    def width(self):
        return self.max_x - self.min_x

    @property
    def height(self):
        return self.max_y - self.min_y

    def as_tuple(self):
        return (self.min_x, self.max_x, self.min_y, self.max_y)

    def contains(self, x, y):
        return self.min_x <= x <= self.max_x and self.min_y <= y <= self.max_y


def info_msg(s: str, quiet: bool = False) -> None:
    """
    Print an informational message if quiet is true.
    """
    if not quiet:
        print(s, file=sys.stdout)

def warning_msg(s: str, quiet: bool = False) -> None:
    """
    Print a warning message if quiet is true.
    """
    if not quiet:
        print(s, file=sys.stderr)
        
def error_msg(s: str) -> None:
    """
    Print an error message (always to stderr).
    """
    print(s, file=sys.stderr)

        
def parse_args() -> argparse.Namespace:
    """
    Parse command-line arguments and return them as a Namespace.
    """
    parser = argparse.ArgumentParser(
        description="Create true-to-scale topographic maps "
                    "or satellite photos from web tiles."
    )
    parser.add_argument(
        "--lat",
        type=float,
        required=True,
        help="latitude of map at paper center (required)"
    )
    parser.add_argument(
        "--lon",
        type=float,
        required=True,
        help="longitude of map at the paper center (required)"
    )
    parser.add_argument(
        "--scale",
        type=int,
        default=25000,
        help="map scale, e.g. 5000 for 1:5000 (default: 25000)",
    )
    parser.add_argument(
        "--zoom",
        type=int,
        default=15,
        help="tile zoom factor, e.g., 14, 15, or 16 (default: 15)",
    )
    parser.add_argument(
        "--provider",
        type=str.lower,
        choices=list(PROVIDERS.keys()),
        default="topographic",
        help="map tile provider (default: topographic)",
    )    
    parser.add_argument(
        "--format",
        type=str.upper,
        choices=list(DIN_FORMATS_MM.keys()),
        default="A4",
        help="DIN paper format (default: A4)",
    )
    parser.add_argument(
        "--orientation",
        type=str.lower,
        choices=["portrait", "landscape"],
        default="landscape",
        help="paper orientation (default: landscape)",
    )
    parser.add_argument(
        "--label",
        type=str,
        default=None,
        help="text in bottom-left box (default: no text box)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default=None,
        help="output file name (default auto-generated based on "
             "map parameters); supported formats pdf, jpg, and png",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="suppress messages (default: false)",
    )
    return parser.parse_args()

def normalize_longitude(lon: float) -> float:
    """
    Normalize longitude to [-180, 180).
    """
    return ((lon + 180) % 360) - 180

def normalize_latitude(lat: float, lon: float) -> Tuple[float, float]:
    """
    Reflect latitude over the poles if out of bounds, adjusting longitude if necessary.
    Returns a tuple (normalized_lat, normalized_lon).
    """
    while lat < -90 or lat > 90:
        if lat > 90:
            lat = 180 - lat
            lon += 180
        elif lat < -90:
            lat = -180 - lat
            lon += 180
    lon = normalize_longitude(lon)
    return lat, lon

def validate_args(args: argparse.Namespace) -> None:
    """
    Validate and normalize coordinate arguments if necessary; warn if normalization occurred.
    Raises an exception if a non-coordinate argument is out of bounds.
    """
    # Normalize and warn if necessary
    if not (-90.0 <= args.lat <= 90.0) or not (-180.0 <= args.lon <= 180.0):
        orig_lat, orig_lon = args.lat, args.lon
        args.lat, args.lon = normalize_latitude(args.lat, args.lon)
        if args.lat != orig_lat:
            warning_msg(f"Latitude {orig_lat} out of range; normalized to {args.lat}", args.quiet)
        if args.lon != orig_lon:
            warning_msg(f"Longitude {orig_lon} out of range; normalized to {args.lon}", args.quiet)
    # Validate scale and zoom as usual
    if not (args.scale > 0 and args.scale < 1_000_000):
        raise MapGenError(f"Error: Scale {args.scale} must be > 0 and < 1,000,000")
    provider_zoom_max = {"topographic": 17, "satellite": 19}
    zoom_min = 0
    zoom_max = provider_zoom_max.get(args.provider, 19)
    if not (zoom_min <= args.zoom <= zoom_max):
        raise MapGenError(f"Error: Zoom {args.zoom} must be between {zoom_min} and "
                          f"{zoom_max} for provider '{args.provider}'")

def determine_output(args: argparse.Namespace) -> tuple[Path, str]:
    """
    Return output Path object and file extension format using. Raises an exception if
    file format is unknown, i.e., path suffix is neither .pdf nor .jpg/.jpeg nor .png.
    """
    filepath = Path(args.output or f"map_{args.provider}_{args.format}_{args.scale}.pdf")
    fileformat = filepath.suffix.lower()
    if fileformat not in {'.pdf', '.jpg', '.jpeg', '.png'}:
        raise MapGenError(f"Unknown file format extension: {fileformat}")
    return filepath, fileformat



def get_paper_size_mm(args: argparse.Namespace) -> Size:
    """
    Get the physical paper size, considering orientation, as a Size.
    """
    width_mm, height_mm = DIN_FORMATS_MM[args.format]
    if args.orientation == "landscape":
        width_mm, height_mm = height_mm, width_mm
    return Size(width_mm, height_mm)

def get_map_size_m(paper_size_mm: Size, scale: int) -> Size:
    """
    Convert paper size (mm) and scale to physical map area in meters.
    """
    width_m = (paper_size_mm.width / 1000.0) * scale
    height_m = (paper_size_mm.height / 1000.0) * scale
    return Size(width_m, height_m)


def calculate_mercator_bounds(lon: float, lat: float, map_size_m: Size) -> tuple[Bounds, float, float]:
    """
    Convert map dimensions and center to mercator projection limits.
    Returns a Bounds object and Mercator center coordinates.
    """
    center_x, center_y = mercantile.xy(lon, lat)
    mercator_scale_factor = 1.0 / math.cos(math.radians(lat))
    half_merc_w = (map_size_m.width * mercator_scale_factor) / 2.0
    half_merc_h = (map_size_m.height * mercator_scale_factor) / 2.0
    min_mx = center_x - half_merc_w
    max_mx = center_x + half_merc_w
    min_my = center_y - half_merc_h
    max_my = center_y + half_merc_h
    return Bounds(min_mx, max_mx, min_my, max_my), center_x, center_y

def determine_tiles(area: Bounds, zoom: int) -> list[Any]:
    """
    Compute the list of map tiles needed to cover the requested area and
    returns the list.
    """
    west, south = mercantile.lnglat(area.min_x, area.min_y)
    east, north = mercantile.lnglat(area.max_x, area.max_y)
    tiles = list(mercantile.tiles(west, south, east, north, zooms=zoom))
    return tiles


def get_tile_boundaries(tiles: list[Any]) -> tuple[Bounds, Size]:
    """
    Compute tile min/max x/y indices and return as Bounds, along
    with needed canvas Size in pixels.
    """
    min_tx = min(t.x for t in tiles)
    max_tx = max(t.x for t in tiles)
    min_ty = min(t.y for t in tiles)
    max_ty = max(t.y for t in tiles)
    canvas_size = Size((max_tx - min_tx + 1) * 256, (max_ty - min_ty + 1) * 256)
    return Bounds(min_tx, max_tx, min_ty, max_ty), canvas_size


def download_and_stitch_tiles(tiles: list[Any], tile_grid: Bounds, canvas_size: Size, args: argparse.Namespace) -> Image.Image:
    """
    Download all needed map tiles and stitch them into a single canvas.
    Retries downloading a tile up to MAX_TILE_DOWNLOAD_RETRIES times before failing.
    Raises an exception if downloading or stitching fails after all retries.
    """
    canvas = Image.new("RGB", (int(canvas_size.width), int(canvas_size.height)))
    
    provider_info = PROVIDERS[args.provider]
    headers = {"User-Agent": provider_info["user_agent"]}
    tqdm_bar = tqdm(tiles, desc="Downloading tiles", disable=args.quiet)
    for idx, t in enumerate(tqdm_bar, 1):
        url = provider_info["url"].format(z=t.z, x=t.x, y=t.y)
        
        last_exception = None
        for attempt in range(1, MAX_TILE_DOWNLOAD_RETRIES + 1):
            try:
                response = requests.get(url, headers=headers, timeout=20)
                if response.status_code == 200: # OK
                    try:
                        tile_img = Image.open(io.BytesIO(response.content)).convert("RGB")
                        x_pos = int(t.x - tile_grid.min_x) * 256
                        y_pos = int(t.y - tile_grid.min_y) * 256
                        canvas.paste(tile_img, (x_pos, y_pos))
                        break  # Success, so exit retry loop
                    except Exception as e:
                        warning_msg(f"Failed to process image for tile {t.x}/{t.y}: {e}", args.quiet)
                        last_exception = e
                        if attempt == MAX_TILE_DOWNLOAD_RETRIES:
                            raise MapGenError(f"Failed to download tiles: {e}")
                else:
                    warning_msg(f"HTTP error at tile {t.x}/{t.y}: {response.status_code}", args.quiet)                    
                    last_exception = f"HTTP {response.status_code}"
                    if attempt == MAX_TILE_DOWNLOAD_RETRIES:
                        raise MapGenError(f"Failed to download tiles: HTTP error {response.status_code}")
            except requests.RequestException as e:
                warning_msg(f"Network error when downloading tile {t.x}/{t.y}: {e}", args.quiet)
                last_exception = e
                if attempt == MAX_TILE_DOWNLOAD_RETRIES:
                    raise MapGenError(f"Failed to download tiles: {e}")
            # Wait some time before starting the next attempt for this tile.
            time.sleep(TILE_DOWNLOAD_RETRY_DELAY)
        else:
            # This else should never be hit, since all terminal exceptions are inside the loop
            raise MapGenError(f"Failed to download tile {t.x}/{t.y}: {last_exception}")
        
        # Wait some time before downloading the next tile.
        time.sleep(0.1)
        
    return canvas

def crop_canvas(canvas: Image.Image, area_bounds: Bounds, grid_bounds: Bounds, canvas_size: Size, zoom: int) -> Image.Image:
    """
    Crop the stitched tile canvas to the correct geographical extent
    using Bounds objects for both the requested map area and the
    projected tile grid bounds. Uses canvas Size.
    """
    min_tx, max_tx, min_ty, max_ty = grid_bounds.min_x, grid_bounds.max_x, grid_bounds.min_y, grid_bounds.max_y
    
    # Get the actual Web Mercator bounding box in meters for the tile grid
    tl_bounds = mercantile.xy_bounds(min_tx, min_ty, zoom)
    br_bounds = mercantile.xy_bounds(max_tx, max_ty, zoom)

    grid_min_x = tl_bounds.left
    grid_max_x = br_bounds.right
    grid_min_y = br_bounds.bottom
    grid_max_y = tl_bounds.top
    
    grid_width = grid_max_x - grid_min_x
    grid_height = grid_max_y - grid_min_y
    
    px_per_m_x = canvas_size.width / grid_width
    px_per_m_y = canvas_size.height / grid_height
    
    crop_left = int(round((area_bounds.min_x - grid_min_x) * px_per_m_x))
    crop_right = int(round((area_bounds.max_x - grid_min_x) * px_per_m_x))
    crop_top = int(round((grid_max_y - area_bounds.max_y) * px_per_m_y))
    crop_bottom = int(round((grid_max_y - area_bounds.min_y) * px_per_m_y))
    
    return canvas.crop((crop_left, crop_top, crop_right, crop_bottom))


def build_label(args: argparse.Namespace) -> str:
    """
    Construct the annotation text for the map (label, scale, etc.).
    """
    box_text = (f"Scale 1:{args.scale}, Latitude {args.lat}, Longitude {args.lon}\n"
                f"{PROVIDERS[args.provider]['copyright']}")
    if args.label is not None and len(args.label) > 0:
        box_text = f"{args.label}\n" + box_text
    return box_text

def add_annotation_box(image: Image.Image, args: argparse.Namespace) -> None:
    """
    Draw annotation box with metadata and label at bottom left of the map.
    """
    try:
        font_size = 16 # max(16, int(image.width / 80))
        font = ImageFont.truetype("arial.ttf", font_size)
    except IOError:
        font = ImageFont.load_default()

    draw = ImageDraw.Draw(image)
    text = build_label(args)
    
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    padding = 5
    margin = 5
    box_width = text_width + (padding * 2)
    box_height = text_height + (padding * 2)
    img_width, img_height = image.size
    x = margin
    y = img_height - box_height - margin
    box_coords = [x, y, x + box_width, y + box_height]
    
    draw.rectangle(box_coords, fill="white", outline="black", width=1)
    draw.text((x + padding, y + padding), text, fill="black", font=font)


def save_output_file(image: Image.Image, output_file: Path, output_format: str, paper_size_mm: Size) -> None:
    """
    Save the final map to disk as PDF, JPG, or PNG.
    Raises an expection in case of a failure.
    """
    output_path = Path(output_file) if not isinstance(output_file, Path) else output_file
    if output_format == ".pdf":
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp_file:
            temp_png = Path(tmp_file.name)
        try:
            image.save(temp_png, "PNG")
            pdf_layout = img2pdf.get_layout_fun((img2pdf.mm_to_pt(paper_size_mm.width),
                                                 img2pdf.mm_to_pt(paper_size_mm.height)))
            with open(output_path, "wb") as f:
                f.write(img2pdf.convert(str(temp_png), layout_fun=pdf_layout))
        except Exception as e:
            raise MapGenError(f"Failed to create or save PDF ('{output_path}'): {e}")
        finally:
            if temp_png.exists():
                temp_png.unlink()
    elif output_format == ".jpg":
        try:
            image.save(output_path, "JPEG", quality=95)
        except Exception as e:
            raise MapGenError(f"Failed to save JPEG ('{output_path}'): {e}")
    elif output_format == ".png":
        try:
            image.save(output_path, "PNG")
        except Exception as e:
            raise MapGenError(f"Failed to save PNG ('{output_path}'): {e}")

def main() -> None:
    """
    Main orchestration: parse args, validate, build map, and save output.
    """
    try:
        args = parse_args()
        validate_args(args)
        filepath, fileformat = determine_output(args)

        # Get paper size (mm) and real map size (meters).
        paper_size_mm = get_paper_size_mm(args)
        map_size_m = get_map_size_m(paper_size_mm, args.scale)
        # Calculate Mercator bounds for the map area.
        area_bounds, center_x, center_y = calculate_mercator_bounds(args.lon, args.lat, map_size_m)
        # Determine tiles to fetch for the requested area.
        tiles = determine_tiles(area_bounds, args.zoom)
        info_msg(f"Provider: {args.provider} ({PROVIDERS[args.provider]['site']})\n"
                 f"Center: {args.lat} (latitude), {args.lon} (longitude)\n"
                 f"Area: {map_size_m.width/1000:.2f} km x {map_size_m.height/1000:.2f} km\n"
                 f"Scale: 1:{args.scale}\n"
                 f"Paper format: {args.format} ({args.orientation})",
                 args.quiet)
        info_msg(f"Total number of tiles for zoom {args.zoom}: {len(tiles)}", args.quiet)

        # Compute tile grid bounds and canvas size (Mercator px bounds).
        grid_bounds, canvas_size = get_tile_boundaries(tiles)
        # Download and stitch all needed tiles.
        canvas = download_and_stitch_tiles(tiles, grid_bounds, canvas_size, args)
        # Crop stitched canvas to exact requested Mercator area.
        cropped_map = crop_canvas(canvas, area_bounds, grid_bounds, canvas_size, args.zoom)
        # Compose label and draw annotation box if --label is given.
        add_annotation_box(cropped_map, args)
        
        # Save map as PDF/JPG/PNG.
        save_output_file(cropped_map, filepath, fileformat, paper_size_mm)
        info_msg(f"Done! Map saved as {filepath}.", args.quiet)
    except MapGenError as e:
        error_msg(str(e))
        sys.exit(1)
    except KeyboardInterrupt:
        error_msg("\nOperation cancelled by user.")
        sys.exit(1)


if __name__ == "__main__":
    main()
