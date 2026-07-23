"""Diagnostic: visualize walls + room-detection internals for one fixture."""
import os, sys
import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from detector import detect_floor_plan

name = sys.argv[1] if len(sys.argv) > 1 else "3br_cad.jpg"
path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", name)

img = cv2.imread(path)
H, W = img.shape[:2]
r = detect_floor_plan(path)

overlay = img.copy()
for w in r["walls"]:
    color = (0, 0, 255) if w["wall_type"] == "main_wall" else (0, 200, 0)
    cv2.line(overlay, (w["x1"], w["y1"]), (w["x2"], w["y2"]), color, 3)

# Fill detected room polygons semi-transparently
room_layer = overlay.copy()
for rm in r["rooms"]:
    poly = np.array(rm["polygon"], dtype=np.int32)
    cv2.fillPoly(room_layer, [poly], (255, 0, 255))
overlay = cv2.addWeighted(room_layer, 0.35, overlay, 0.65, 0)
for rm in r["rooms"]:
    b = rm["bbox"]
    cv2.putText(overlay, f'{rm["id"]} {int(rm["area"])}', (b["x"] + 5, b["y"] + 25),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 255), 2)

for o in r["openings"]:
    cx, cy = int(o.get("x", 0)), int(o.get("y", 0))
    col = (255, 128, 0) if o["type"] == "door" else (0, 255, 255)
    cv2.circle(overlay, (cx, cy), 14, col, 3)

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"diag_{name}.png")
cv2.imwrite(out, overlay)
print(f"walls={len(r['walls'])} rooms={len(r['rooms'])} openings={len(r['openings'])}")
print(f"room areas: {[int(rm['area']) for rm in r['rooms']]}")
print(f"image area: {W*H}, min_room_area(0.1%)={int(W*H*0.001)}")
print(f"saved {out}")
