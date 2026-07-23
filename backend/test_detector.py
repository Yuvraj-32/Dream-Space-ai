import sys, glob, os, time
sys.path.insert(0, '.')
from detector import detect_floor_plan

# ── Find test image ───────────────────────────────────────────────
# Prefer the largest image in uploads/ (most informative for testing)
files = glob.glob('uploads/*.jpg') + glob.glob('uploads/*.webp') + glob.glob('uploads/*.png')

# Fallback to known project image
if not files:
    candidate = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "67ca2328a5aebddb6989e0c8_30x40 3 Bedroom Floor Plan.jpg")
    if os.path.exists(candidate):
        files = [candidate]

if not files:
    print('No test image found.')
    exit(1)

# Pick the LARGEST file (best quality floor plan)
img = max(files, key=os.path.getsize)
print(f'Testing: {img}  ({os.path.getsize(img)//1024} KB)\n')

# ── Run detection ─────────────────────────────────────────────────
t0 = time.time()
result = detect_floor_plan(img)
elapsed = time.time() - t0

s = result['stats']

# ── Print full pipeline breakdown ─────────────────────────────────
W = 54
print('=' * W)
print(f'  DreamSpace Detector v3  ({elapsed:.2f}s)')
print('=' * W)
print(f'  Image:           {s["image_size"]["width"]} x {s["image_size"]["height"]} px')
print(f'  Scale used:      {s.get("processing_scale", 1.0)}')
print()
print('  ── Line Detection ──────────────────────────────')
print(f'  Raw lines:       {s.get("raw_lines", "?")}')
print(f'  After merge p1:  {s.get("after_merge_p1", "?")}')
print(f'  After merge p2:  {s.get("after_merge_p2", "?")}')
print(f'  After length:    {s.get("after_length_filter", "?")}')
print(f'  Thickness filter:{s.get("thickness_filter", "?")}  → {s.get("after_thickness","?")}')
print(f'  After ep-snap:   {s.get("after_endpoint_snap","?")}')
print(f'  After coaxial:   {s.get("after_coaxial_merge","?")}')
print(f'  After isolated:  {s.get("after_isolated_removal","?")}')
print()
print('  ── Final Results ───────────────────────────────')
print(f'  WALLS:           {len(result["walls"])}')
print(f'    main_wall:     {s.get("main_walls","?")}  (bold structural walls)')
print(f'    partition:     {s.get("partition_walls","?")}  (slim interior dividers)')
print(f'    faded discarded: (filtered before classification)')
print(f'    thickness split: {s.get("thickness_main_thresh","?")}px')
print(f'  ROOMS:           {len(result["rooms"])}')
print(f'  OPENINGS:        {len(result["openings"])}  '
      f'(doors={s.get("doors",0)}, windows={s.get("windows",0)})')
print(f'  DOOR ARCS:       {s.get("door_arcs_found", 0)}')
print()

# ── Top walls ────────────────────────────────────────────────────
print('  Top 10 walls by length:')
top = sorted(result['walls'], key=lambda w: w['length'], reverse=True)[:10]
for w in top:
    print(f'    {w["id"]:12s}  {w["length"]:>6.0f}px  {w["angle"]:>6.1f}°')

# ── Rooms ────────────────────────────────────────────────────────
if result['rooms']:
    print()
    print('  Rooms:')
    for r in result['rooms'][:8]:
        b = r['bbox']
        cx = r.get('centroid', {}).get('x', '?')
        cy = r.get('centroid', {}).get('y', '?')
        print(f'    {r["id"]:12s}  {r["area"]/1000:>6.1f}k px²  '
              f'{b["w"]:>4}x{b["h"]:<4}  center=({cx},{cy})')

# ── Openings ─────────────────────────────────────────────────────
if result['openings']:
    print()
    print('  Openings (first 12):')
    for o in result['openings'][:12]:
        arc = '🚪arc' if 'arc_x' in o else ''
        print(f'    {o["id"]:16s}  {o["type"]:6s}  {o["width_px"]:>5.0f}px  '
              f'wall={o["wall_id"]}  {arc}')
else:
    print()
    print('  No openings detected.')

print()
print('=' * W)
