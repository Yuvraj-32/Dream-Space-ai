"""Fast cluster thumbnails drawn straight from flattened line segments with OpenCV.

Phase 0 rendered whole sheets with ezdxf's matplotlib backend in up to 47 s;
these thumbnails only need to be recognisable, so plain line drawing is used
(well under a second). Colours follow the suggested layer roles, so the
thumbnail doubles as a preview of what will become walls/doors/windows.
"""
import cv2
import numpy as np

from .vocab import room_type_for

BG = (36, 24, 20)            # BGR of #141824
LABEL_COLOR = (80, 215, 255)  # amber
ROLE_STYLE = {                # BGR colour, thickness
    "wall": ((245, 245, 245), 2),
    "door": ((80, 200, 255), 1),
    "window": ((230, 200, 60), 1),
    "room_label": ((150, 150, 150), 1),
    "ignore": ((110, 98, 90), 1),
}


def render_cluster(records, rec_idxs, bbox, layer_roles, out_path, max_w=360, max_h=270, margin=10):
    x0, y0, x1, y1 = bbox
    w_u, h_u = max(x1 - x0, 1e-9), max(y1 - y0, 1e-9)
    scale = min((max_w - 2 * margin) / w_u, (max_h - 2 * margin) / h_u)
    w = max(40, int(round(w_u * scale)) + 2 * margin)
    h = max(40, int(round(h_u * scale)) + 2 * margin)
    _draw(records, rec_idxs, layer_roles, out_path, w, h, x0, y1, scale, margin, margin, font=0.3)
    return w, h


def render_preview(records, rec_idxs, layer_roles, out_path, width, height, x0, y1, scale, ox, oy):
    """Full-size background for the 2D editor, in exactly the detection's pixel space:
    px = (x - x0) * scale + ox, py = (y1 - y) * scale + oy (drawing units)."""
    _draw(records, rec_idxs, layer_roles, out_path, width, height, x0, y1, scale, ox, oy, font=0.5)


def _draw(records, rec_idxs, layer_roles, out_path, w, h, x0, y1, scale, ox, oy, font):
    img = np.full((h, w, 3), BG, dtype=np.uint8)

    by_role = {role: [] for role in ROLE_STYLE}
    for i in rec_idxs:
        r = records[i]
        if not r.segs:
            continue
        by_role[layer_roles.get(r.layer, "ignore")].extend(r.segs)

    for role in ("ignore", "room_label", "window", "door", "wall"):
        segs = by_role[role]
        if not segs:
            continue
        s = np.asarray(segs, dtype=np.float64)
        pts = np.empty((len(s), 2, 2), dtype=np.int32)  # contiguous: OpenCV 5 rejects strided views
        pts[:, :, 0] = np.round((s[:, [0, 2]] - x0) * scale + ox)
        pts[:, :, 1] = np.round((y1 - s[:, [1, 3]]) * scale + oy)
        color, thickness = ROLE_STYLE[role]
        cv2.polylines(img, list(pts), isClosed=False, color=color, thickness=thickness, lineType=cv2.LINE_AA)

    for i in rec_idxs:
        r = records[i]
        if r.text and room_type_for(r.text):
            label = r.text if len(r.text) <= 18 else r.text[:17] + "…"
            px = int(round((r.bbox[0] - x0) * scale + ox))
            py = int(round((y1 - r.bbox[1]) * scale + oy))
            cv2.putText(img, label.encode("ascii", "replace").decode(), (px, py),
                        cv2.FONT_HERSHEY_SIMPLEX, font, LABEL_COLOR, 1, cv2.LINE_AA)

    cv2.imwrite(out_path, img)
