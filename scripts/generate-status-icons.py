"""Generate the bundled keycap icons and their SVG sources.

Run with Python 3 and Pillow: python3 scripts/generate-status-icons.py
All dimensions are in an 18-point grid; artwork is supersampled before
downsampling. ICOs use BMP entries for Windows LoadImage compatibility.
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
SCALE = 64
WHITE = (255, 255, 255, 255)

# The common shell and top face make a blank, slightly raised keycap.
SHELL = [
    ('roundrect', (2, 2, 16, 16), 3, 1.25),
    ('roundrect', (4, 3.75, 14, 12.25), 1.75, 1),
    ('line', ((4.5, 12), (3, 14.75)), 1),
    ('line', ((13.5, 12), (15, 14.75)), 1),
]
MARKS = {
    'default': [],
    'pause': [('line', ((7.4, 6), (7.4, 10)), 1.35),
              ('line', ((10.6, 6), (10.6, 10)), 1.35)],
    'crash': [('line', ((9, 5.65), (9, 8.3)), 1.35),
              ('dot', (9, 10), 0.7)],
    'live-reload': [('arc', (6.4, 5.5, 11.6, 10.7), 35, 310, 1.1),
                    ('polygon', ((10, 5.45), (12, 5.9), (11.5, 7.8)))],
}


def scaled(values):
    return tuple(round(value * SCALE) for value in values)


def render(shapes):
    image = Image.new('RGBA', (18 * SCALE, 18 * SCALE))
    draw = ImageDraw.Draw(image)
    for shape in shapes:
        kind, *args = shape
        if kind == 'roundrect':
            box, radius, width = args
            # Pillow places outlines inside the box; expand by half a stroke
            # to match the centered SVG outline.
            x0, y0, x1, y1 = box
            half = width / 2
            draw.rounded_rectangle(scaled((x0-half, y0-half, x1+half, y1+half)),
                                   radius=round((radius+half)*SCALE),
                                   outline=WHITE, width=round(width*SCALE))
        elif kind == 'line':
            points, width = args
            draw.line([scaled(point) for point in points], fill=WHITE, width=round(width*SCALE))
            for x, y in points:
                r = width / 2
                draw.ellipse(scaled((x-r, y-r, x+r, y+r)), fill=WHITE)
        elif kind == 'dot':
            (x, y), r = args
            draw.ellipse(scaled((x-r, y-r, x+r, y+r)), fill=WHITE)
        elif kind == 'arc':
            box, start, end, width = args
            draw.arc(scaled(box), start, end, fill=WHITE, width=round(width*SCALE))
        elif kind == 'polygon':
            draw.polygon([scaled(point) for point in args[0]], fill=WHITE)
        else:
            raise ValueError(kind)
    return image


def svg(shapes):
    import math
    elements = []
    for kind, *args in shapes:
        if kind == 'roundrect':
            (x0, y0, x1, y1), radius, width = args
            elements.append(f'<rect x="{x0}" y="{y0}" width="{x1-x0}" height="{y1-y0}" rx="{radius}" stroke-width="{width}"/>')
        elif kind == 'line':
            points, width = args
            coords = ' '.join(f'{x},{y}' for x, y in points)
            elements.append(f'<polyline points="{coords}" stroke-width="{width}"/>')
        elif kind == 'dot':
            (x, y), radius = args
            elements.append(f'<circle cx="{x}" cy="{y}" r="{radius}" fill="white" stroke="none"/>')
        elif kind == 'polygon':
            coords = ' '.join(f'{x},{y}' for x, y in args[0])
            elements.append(f'<polygon points="{coords}" fill="white" stroke="none"/>')
        elif kind == 'arc':
            (x0, y0, x1, y1), start, end, width = args
            cx, cy, r = (x0+x1)/2, (y0+y1)/2, (x1-x0)/2
            point = lambda a: (cx+r*math.cos(math.radians(a)), cy+r*math.sin(math.radians(a)))
            x, y = point(start)
            u, v = point(end)
            elements.append(f'<path d="M{x:.4f},{y:.4f} A{r},{r} 0 1 1 {u:.4f},{v:.4f}" stroke-width="{width}"/>')
    return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 18 18" fill="none" stroke="white" stroke-linecap="round" stroke-linejoin="round">\n  ' + '\n  '.join(elements) + '\n</svg>\n'


def main():
    source = ROOT / 'status_icons' / 'sources'
    source.mkdir(exist_ok=True)
    rendered = {}
    for name, marks in MARKS.items():
        shapes = SHELL + marks
        (source / f'{name}.svg').write_text(svg(shapes))
        icon = render(shapes).resize((128, 128), Image.Resampling.LANCZOS)
        # Keep straight RGB white even on antialiased transparent pixels.
        alpha = icon.getchannel('A')
        icon = Image.new('RGBA', icon.size, WHITE)
        icon.putalpha(alpha)
        icon.save(ROOT / 'status_icons' / f'{name}.ico', bitmap_format='bmp',
                  sizes=[(s, s) for s in [16, 32, 48, 64, 128]])
        rendered[name] = icon
    rendered['default'].save(ROOT / 'status_icons' / '128x128.png')

    sheet = Image.new('RGB', (760, 296), '#23252a')
    sheet.paste('#f4f4f5', (0, 148, 760, 296))
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default(size=16)
    small = ImageFont.load_default(size=12)
    for row, color in [(0, 'white'), (148, '#18191c')]:
        draw.text((20, row+18), 'Dark menu bar' if row == 0 else 'Light menu bar', font=font, fill=color)
        for i, (name, icon) in enumerate(rendered.items()):
            x = 210 + i*140
            tinted = Image.new('RGBA', icon.size, color)
            tinted.putalpha(icon.getchannel('A'))
            for size, dx, dy in [(64, 0, 44), (16, 78, 66)]:
                thumb = tinted.resize((size, size), Image.Resampling.LANCZOS)
                sheet.paste(thumb, (x+dx, row+dy), thumb)
            draw.text((x, row+116), {'default':'Normal', 'pause':'Paused', 'crash':'Error', 'live-reload':'Reload'}[name], font=small, fill=color)
    assets = ROOT / 'doc' / 'assets'
    assets.mkdir(exist_ok=True)
    sheet.save(assets / 'status-icons-preview.png')


if __name__ == '__main__':
    main()
