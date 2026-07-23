import os
import sys, time
sys.path.insert(0, '.')
from detector import detect_floor_plan

img = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "67ca2328a5aebddb6989e0c8_30x40 3 Bedroom Floor Plan.webp")
t0 = time.time()
r = detect_floor_plan(img)
elapsed = time.time() - t0

s = r['stats']
W = 58
print('=' * W)
print(f'  TARGET IMAGE ANALYSIS  ({elapsed:.2f}s)')
print('=' * W)
imsz = s['image_size']
print(f'  Image: {imsz["width"]} x {imsz["height"]}')
print(f'  Scale: {s.get("processing_scale", 1.0)}')
print()
print('  -- Pipeline --')
print(f'  Raw lines:       {s.get("raw_lines", "?")}')
print(f'  After merge p1:  {s.get("after_merge_p1", "?")}')
print(f'  After merge p2:  {s.get("after_merge_p2", "?")}')
print(f'  After length:    {s.get("after_length_filter", "?")}')
print(f'  Thickness:       {s.get("thickness_filter", "?")} -> {s.get("after_thickness", "?")}')
print(f'  After ep-snap:   {s.get("after_endpoint_snap", "?")}')
print(f'  After coaxial:   {s.get("after_coaxial_merge", "?")}')
print(f'  After isolated:  {s.get("after_isolated_removal", "?")}')
print()
print('  -- Results --')
print(f'  WALLS:     {len(r["walls"])}  (main={s.get("main_walls","?")}, partition={s.get("partition_walls","?")})')
print(f'  ROOMS:     {len(r["rooms"])}')
print(f'  OPENINGS:  {len(r["openings"])}  (doors={s.get("doors",0)}, windows={s.get("windows",0)})')
print(f'  ARCS:      {s.get("door_arcs_found", 0)}')
print(f'  Main/Part threshold: {s.get("thickness_main_thresh", "?")}')
print()

print('  -- ALL WALLS --')
for w in r['walls']:
    tag = 'MAIN' if w['wall_type'] == 'main_wall' else 'part'
    print(f'    {w["id"]:12s}  len={w["length"]:>6.0f}px  '
          f'angle={w["angle"]:>6.1f}  {tag:4s}  thick={w["thickness"]:.1f}')
print()

print('  -- OPENINGS --')
for o in r['openings']:
    arc = 'ARC' if 'arc_x' in o else '   '
    print(f'    {o["id"]:16s}  {o["type"]:6s}  w={o["width_px"]:>5.0f}px  '
          f'wall={o["wall_id"]}  {arc}')
print()

print('  -- ROOMS --')
for rm in r['rooms']:
    b = rm['bbox']
    cx, cy = rm['centroid']['x'], rm['centroid']['y']
    print(f'    {rm["id"]:12s}  area={rm["area"]/1000:.1f}k px2  '
          f'{b["w"]}x{b["h"]}  center=({cx},{cy})')
print()
print('=' * W)
