#!/usr/bin/python3

import argparse
from dataclasses import dataclass
import io
import math
import os
import sys
import time

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
        "copyright": "Map Data: © OpenStreetMap Contributors, SRTM\nMap Style: © OpenTopoMap (CC-BY-SA)"
    },
    "satellite": {
        "site": "https://server.arcgisonline.com",
        "url": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        "user_agent": "PrivateSatelliteMapProject/1.0 (kontakt@beispiel.at)",
        "is_y_inverted": True,
        "copyright": "Map image is the intellectual property of Esri and is used herein under license.\n© 2026 Esri and its licensors. All rights reserved."
    }
}


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


def info(b, s):
    """
    Print an informational message if b is true.
    """
    if not b:
        print(s, file=sys.stdout)

def warning(b, s):
    """
    Print a warning message unless if b is true.
    """
    if not b:
        print(s, file=sys.stderr)

def error(b, s):
    """
    Print an error message (always to stderr).
    """
    print(s, file=sys.stderr)

        
def parse_args():
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
        help="output file name (default auto-generated based on map parameters); supported formats pdf, jpg, and png",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="suppress messages (default: false)",
    )
    return parser.parse_args()

def validate_args(args):
    """
    Validate the parsed arguments for allowed value ranges.  Print
    an error and exit if any value is invalid.
    """
    if not (-90.0 <= args.lat <= 90.0):
        error(args.quiet,
              f"Error: Latitude {args.lat} out of valid range (-90 to 90)")
        sys.exit(1)
    if not (-180.0 <= args.lon <= 180.0):
        error(args.quiet,
              f"Error: Longitude {args.lon} out of valid range (-180 to 180)")
        sys.exit(1)
    if not (args.scale > 0 and args.scale < 1_000_000):
        error(args.quiet,
              f"Error: Scale {args.scale} must be > 0 and < 1,000,000")
        sys.exit(1)
    provider_zoom_max = {"topographic": 17, "satellite": 19}
    zoom_min = 0
    zoom_max = provider_zoom_max.get(args.provider, 19)
    if not (zoom_min <= args.zoom <= zoom_max):
        error(args.quiet,
              f"Error: Zoom {args.zoom} must be between {zoom_min} and {zoom_max} "
              f"for provider '{args.provider}'")
        sys.exit(1)

def determine_output(args):
    """
    Return the output file name (auto-generate one if not supplied) and its format,
    which is given by the file name's extension, e.g., '.pdf', '.jpg', ...
    """
    filename = args.output or f"map_{args.provider}_{args.format}_{args.scale}.pdf"
    return filename, os.path.splitext(filename)[1].lower()


def get_paper_size_mm(args) -> Size:
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


def calculate_mercator_bounds(args, map_size_m: Size):
    """
    Convert map dimensions and center to mercator projection
    limits.  Returns a Bounds object and Mercator center coordinates.
    """
    center_x, center_y = mercantile.xy(args.lon, args.lat)
    mercator_scale_factor = 1.0 / math.cos(math.radians(args.lat))
    half_merc_w = (map_size_m.width * mercator_scale_factor) / 2.0
    half_merc_h = (map_size_m.height * mercator_scale_factor) / 2.0
    min_mx = center_x - half_merc_w
    max_mx = center_x + half_merc_w
    min_my = center_y - half_merc_h
    max_my = center_y + half_merc_h
    return Bounds(min_mx, max_mx, min_my, max_my), center_x, center_y

def determine_tiles(min_mx, max_mx, min_my, max_my, args):
    """
    Compute the list of map tiles needed to cover the requested
    area.  Returns a tuple (tiles list, west, south, east, north).
    """
    west, south = mercantile.lnglat(min_mx, min_my)
    east, north = mercantile.lnglat(max_mx, max_my)
    tiles = list(mercantile.tiles(west, south, east, north, zooms=args.zoom))
    return tiles


def get_tile_boundaries(tiles, args):
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


def download_and_stitch_tiles(tiles, tile_grid: Bounds, canvas_size: Size, args):
    """
    Download all needed map tiles and stitch them into a single
    canvas.  Abort on the first error.
    """
    provider_info = PROVIDERS[args.provider]
    headers = {"User-Agent": provider_info["user_agent"]}
    canvas = Image.new("RGB", (int(canvas_size.width), int(canvas_size.height)))
    tqdm_bar = tqdm(tiles, desc="Downloading tiles", disable=args.quiet)
    for idx, t in enumerate(tqdm_bar, 1):
        url = provider_info["url"].format(z=t.z, x=t.x, y=t.y)
        try:
            response = requests.get(url, headers=headers, timeout=20)
        except requests.RequestException as e:
            error(args.quiet, f"Network error when downloading tile {t.x}/{t.y}: {e}")
            sys.exit(1)
        if response.status_code == 200:
            try:
                tile_img = Image.open(io.BytesIO(response.content)).convert("RGB")
            except Exception as e:
                error(args.quiet, f"Failed to process image for tile {t.x}/{t.y}: {e}")
                sys.exit(1)
            x_pos = int(t.x - tile_grid.min_x) * 256
            y_pos = int(t.y - tile_grid.min_y) * 256
            canvas.paste(tile_img, (x_pos, y_pos))
        else:
            error(args.quiet, f"HTTP error at tile {t.x}/{t.y}: HTTP {response.status_code}")
            sys.exit(1)
        time.sleep(0.1)
    return canvas

def crop_canvas(canvas, area_bounds: Bounds, grid_bounds: Bounds, canvas_size: Size):
    """
    Crop the stitched tile canvas to the correct geographical extent
    using Bounds objects for both the requested map area and the
    projected tile grid bounds. Uses canvas Size.
    """
    px_per_m_x = canvas_size.width / grid_bounds.width
    px_per_m_y = canvas_size.height / grid_bounds.height
    crop_left = int(round((area_bounds.min_x - grid_bounds.min_x) * px_per_m_x))
    crop_right = int(round((area_bounds.max_x - grid_bounds.min_x) * px_per_m_x))
    crop_top = int(round((grid_bounds.max_y - area_bounds.max_y) * px_per_m_y))
    crop_bottom = int(round((grid_bounds.max_y - area_bounds.min_y) * px_per_m_y))
    return canvas.crop(crop_left, crop_top, crop_right, crop_bottom)


def build_label(provider_info, args):
    """
    Construct the annotation text for the map (label, scale, etc.).
    """
    box_text = (f"Scale 1:{args.scale}, Latitude {args.lat}, Longitude {args.lon}\n"
                f"{provider_info['copyright']}")
    if args.label is not None and len(args.label) > 0:
        box_text = f"{args.label}\n" + box_text
    return box_text

def add_annotation_box(image, args):
    """
    Draw annotation box with metadata and label at bottom left of the map.
    """
    draw = ImageDraw.Draw(image)
    try:
        font_size = max(16, int(image.width / 80))
        font = ImageFont.truetype("arial.ttf", font_size)
    except IOError:
        font = ImageFont.load_default()
        
    provider_info = PROVIDERS[args.provider]
    text = build_label(provider_info, args)       
    if text.strip():
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


def save_output_file(image, output_file, output_format, paper_size_mm: Size, quiet):
    """
    Save the final map to disk as PDF, JPG, or PNG. Clean up on error.
    """
    if output_format == ".pdf":
        temp_png = "tmp_cropped_map.png"
        try:
            image.save(temp_png, "PNG")
        except Exception as e:
            error(quiet, f"Failed to save temporary PNG ('{temp_png}'): {e}")
            sys.exit(1)
        try:
            pdf_layout = img2pdf.get_layout_fun((img2pdf.mm_to_pt(paper_size_mm.width),
                                                 img2pdf.mm_to_pt(paper_size_mm.height)))
            with open(output_file, "wb") as f:
                f.write(img2pdf.convert(temp_png, layout_fun=pdf_layout))
        except Exception as e:
            error(quiet, f"Failed to create or save PDF ('{output_file}'): {e}")
            if os.path.exists(temp_png):
                os.remove(temp_png)
            sys.exit(1)
        if os.path.exists(temp_png):
            os.remove(temp_png)
    elif output_format == ".jpg":
        try:
            image.save(output_file, "JPEG", quality=95)
        except Exception as e:
            error(quiet, f"Failed to save JPEG ('{output_file}'): {e}")
            sys.exit(1)
    elif output_format == ".png":
        try:
            image.save(output_file, "PNG")
        except Exception as e:
            error(quiet, f"Failed to save PNG ('{output_file}'): {e}")
            sys.exit(1)

def main():
    """
    Main orchestration: parse args, validate, build map, and save output.
    """
    args = parse_args()
    validate_args(args)

    filename, fileformat = determine_output(args)
    if fileformat not in {'.pdf', '.jpg', '.jpeg', '.png'}:
        error(args.quiet, f"Unknown file format: {output_format}")
        sys.exit(1)

    # Get paper size (mm) and real map size (meters).
    paper_size_mm = get_paper_size_mm(args)
    map_size_m = get_map_size_m(paper_size_mm, args.scale)
    # Calculate Mercator bounds for the map area.
    area_bounds, center_x, center_y = calculate_mercator_bounds(args, map_size_m)
    # Determine tiles to fetch for the requested area.
    tiles = determine_tiles(area_bounds.min_x, area_bounds.max_x,
                            area_bounds.min_y, area_bounds.max_y, args)
    info(args.quiet,
         f"Provider: {args.provider}\n"
         f"Center: {args.lat} (latitude), {args.lon} (longitude)\n"
         f"Area: {map_size_m.width/1000:.2f} km x {map_size_m.height/1000:.2f} km\n"
         f"Scale: 1:{args.scale}\n"
         f"Paper format: {args.format} ({args.orientation})")
    info(args.quiet,
         f"Total number of tiles for zoom {args.zoom}: {len(tiles)}")

    # Compute tile grid bounds and canvas size (Mercator px bounds).
    grid_bounds, canvas_size = get_tile_boundaries(tiles, args)
    # Download and stitch all needed tiles.
    canvas = download_and_stitch_tiles(tiles, grid_bounds, canvas_size, args)
    # Crop stitched canvas to exact requested Mercator area.
    cropped_map = crop_canvas(canvas, area_bounds, grid_bounds, canvas_size)
    # Compose label and draw annotation box if --label is given.
    add_annotation_box(cropped_map, args)

    # Save map as PDF/JPG/PNG.
    save_output_file(cropped_map, filename, fileformat, paper_size_mm, args.quiet)
    info(args.quiet, f"Done! Map saved as {output_file}.")


if __name__ == "__main__":
    main()
#    try:
#        main()
#    except Exception as e:
#        print(f"Fatal error: {e}", file=sys.stderr)
#        sys.exit(1)

