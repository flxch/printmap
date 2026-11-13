#!/usr/bin/python3

import argparse
import io
import math
import os
import sys
import time
import requests
import mercantile
from PIL import Image, ImageDraw, ImageFont
import img2pdf
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


def info(b, s):
    if !b:
        print(s, file=sys.stdout)

def warning(b, s):
    if !b:
        print(s, file=sys.stderr)

def error(b, s):
    if !b:
        print(s, file=sys.stderr)

        
def parse_args():
    parser = argparse.ArgumentParser(
        description="Create true-to-scale topographic maps or satellite photos from web tiles."
    )
    parser.add_argument(
        "--lat",
        type=float,
        required=True,
        help="latitude of map at paper center (required)",
    )
    parser.add_argument(
        "--lon",
        type=float,
        required=True,
        help="longitude of map at the paper center (required)",
    )
    parser.add_argument(
        "--scale",
        type=int,
        default=25000,
        help="scale, e.g. 5000 for 1:5000 (default: 25000)",
    )
    parser.add_argument(
        "--zoom",
        type=int,
        default=15,
        help="tile zoom, e.g., 14, 15, or 16 (default: 15)",
    )
    parser.add_argument(
        "--provider",
        type=str.lower,
        choices=list(PROVIDERS.keys()),
        default="topographic",
        help="Map tile provider: topographic or satellite (default: topographic)",
    )    
    parser.add_argument(
        "--format",
        type=str.upper,
        choices=list(DIN_FORMATS_MM.keys()),
        default="A4",
        help="paper format (DIN): A0, A1, A2, A3, or A4 (default: A4)",
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
        help="Custom text for the bottom-left text box (default: no text box)",
    )
    parser.add_argument(
        "--output-format",
        type=str.lower,
        choices=["pdf", "jpg", "png"],
        default="pdf",
        help="Output file format: pdf, jpg, or png (default: pdf)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default=None,
        help="output file name (default auto-generated based on format)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress output (default: False)",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    # Determine output file and format
    ext = args.output_format
    output_file = args.output or f"map_{args.provider}_{args.format}_{args.scale}.{ext}"

    # If the user supplied an output file, try to infer format from its extension
    # unless output_format is explicitly set (default output_format is 'pdf')
    valid_exts = {'.pdf': 'pdf', '.jpg': 'jpg', '.jpeg': 'jpg', '.png': 'png'}
    if args.output:
        file_ext = os.path.splitext(args.output)[1].lower()
        if file_ext in valid_exts:
            # Only override if --output-format is default ('pdf') or not set
            if args.output_format == 'pdf':
                ext = valid_exts[file_ext]
                output_file = args.output
    if args.output_format != ext:
        warning(args.quiet, f"Warning: File suffix does not match the file format.")

    # 1. Paper size and orientation.
    width_mm, height_mm = DIN_FORMATS_MM[args.format]
    if args.orientation == "landscape":
        width_mm, height_mm = height_mm, width_mm

    # 2. Covered area in meters and correction (mercator).
    real_width_m = (width_mm / 1000.0) * args.scale
    real_height_m = (height_mm / 1000.0) * args.scale

    center_x, center_y = mercantile.xy(args.lon, args.lat)
    mercator_scale_factor = 1.0 / math.cos(math.radians(args.lat))

    half_merc_w = (real_width_m * mercator_scale_factor) / 2.0
    half_merc_h = (real_height_m * mercator_scale_factor) / 2.0

    min_mx = center_x - half_merc_w
    max_mx = center_x + half_merc_w
    min_my = center_y - half_merc_h
    max_my = center_y + half_merc_h

    west, south = mercantile.lnglat(min_mx, min_my)
    east, north = mercantile.lnglat(max_mx, max_my)

    # Print some information about the output.
    info(args.quiet,
         f"""
         Provider: {args.provider}
         Center: {args.lat} (latitude), {args.lon} (longitude)
         Area: {real_width_m/1000:.2f} km x {real_height_m/1000:.2f} km
         Scale: 1:{args.scale}
         Paper format: {args.format} ({args.orientation})
         """)

    # 3. Download tiles and put them together.
    tiles = list(mercantile.tiles(west, south, east, north, zooms=args.zoom))
    info(args.quiet, f"Total number of tiles for zoom {args.zoom}: {len(tiles)}")

    min_tx = min(t.x for t in tiles)
    max_tx = max(t.x for t in tiles)
    min_ty = min(t.y for t in tiles)
    max_ty = max(t.y for t in tiles)

    canvas_w = (max_tx - min_tx + 1) * 256
    canvas_h = (max_ty - min_ty + 1) * 256
    canvas = Image.new("RGB", (canvas_w, canvas_h))

    provider_info = PROVIDERS[args.provider]
    headers = {"User-Agent": provider_info["user_agent"]}

    tqdm_bar = tqdm(tiles, desc="Downloading tiles", disable=args.quiet)
    for idx, t in enumerate(tqdm_bar, 1):
        # Format URL template depending on the tile provider's coordinate
        # layout schema
        url = provider_info["url"].format(z=t.z, x=t.x, y=t.y)
        
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            tile_img = Image.open(io.BytesIO(response.content)).convert("RGB")
            x_pos = (t.x - min_tx) * 256
            y_pos = (t.y - min_ty) * 256
            canvas.paste(tile_img, (x_pos, y_pos))
        else:
            error(args.quiet, f"Error at tile {t.x}/{t.y}: HTTP {response.status_code}")
            # Will be an empty tile in the picture.
            
        time.sleep(0.1)

    # 4. Crop map at borders.
    top_left_bounds = mercantile.xy_bounds(min_tx, min_ty, args.zoom)
    bottom_right_bounds = mercantile.xy_bounds(max_tx, max_ty, args.zoom)

    grid_min_mx = top_left_bounds.left
    grid_max_my = top_left_bounds.top
    grid_max_mx = bottom_right_bounds.right
    grid_min_my = bottom_right_bounds.bottom

    px_per_m_x = canvas_w / (grid_max_mx - grid_min_mx)
    px_per_m_y = canvas_h / (grid_max_my - grid_min_my)

    crop_left = int(round((min_mx - grid_min_mx) * px_per_m_x))
    crop_right = int(round((max_mx - grid_min_mx) * px_per_m_x))
    crop_top = int(round((grid_max_my - max_my) * px_per_m_y))
    crop_bottom = int(round((grid_max_my - min_my) * px_per_m_y))

    cropped_map = canvas.crop((crop_left, crop_top, crop_right, crop_bottom))

    # 5. Add text box at bottom-left.
    draw = ImageDraw.Draw(cropped_map)
    try:
        # Scale font size slightly relative to image dimensions for readability.
        font_size = max(16, int(cropped_map.width / 80))
        font = ImageFont.truetype("arial.ttf", font_size)
    except IOError:
        font = ImageFont.load_default()
    # Default to displaying map metadata if no explicit --label is provided.
    if args.label is not None:
        box_text = f"Scale 1:{args.scale}, Latitude {args.lat}, Longitude {args.lon}\n{provider_info['copyright']}"
        if len(args.label) > 0:
            box_text = f"{args.label}\n" + box_text 
        if box_text.strip():
            bbox = draw.textbbox((0, 0), box_text, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
        
            padding = 5
            margin = 5
            box_width = text_width + (padding * 2)
            box_height = text_height + (padding * 2)
        
            img_width, img_height = cropped_map.size
            x = margin
            y = img_height - box_height - margin
        
            box_coords = [x, y, x + box_width, y + box_height]
        
            # Draw white background box with a thin black border
            draw.rectangle(box_coords, fill="white", outline="black", width=1)
            # Draw black text inside the box
            draw.text((x + padding, y + padding), box_text, fill="black", font=font)
        
    # 6. Save output file (PDF, JPG, or PNG).
    if args.output_format == "pdf":
        temp_png = "tmp_cropped_map.png"
        cropped_map.save(temp_png, "PNG")

        pdf_layout = img2pdf.get_layout_fun(
            (img2pdf.mm_to_pt(width_mm), img2pdf.mm_to_pt(height_mm))
        )
        with open(output_file, "wb") as f:
            f.write(img2pdf.convert(temp_png, layout_fun=pdf_layout))

        if os.path.exists(temp_png):
            os.remove(temp_png)
    elif args.output_format == "jpg":
        cropped_map.save(output_file, "JPEG", quality=95)
    elif args.output_format == "png":
        cropped_map.save(output_file, "PNG")

    info(args.quiet, f"Done! Map saved as {output_file}.")


if __name__ == "__main__":
    main()
    
