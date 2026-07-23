import os
import urllib.request, json, os

file_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "67ca2328a5aebddb6989e0c8_30x40 3 Bedroom Floor Plan.jpg")
boundary = b"----FormBoundary7MA4YWxkTrZu0gW"

with open(file_path, "rb") as f:
    file_data = f.read()

disp = b'Content-Disposition: form-data; name="file"; filename="floor_plan.jpg"'
ctype = b"Content-Type: image/jpeg"

body = (
    b"--" + boundary + b"\r\n" +
    disp + b"\r\n" +
    ctype + b"\r\n" +
    b"\r\n" +
    file_data +
    b"\r\n--" + boundary + b"--\r\n"
)

ct = "multipart/form-data; boundary=" + boundary.decode()
req = urllib.request.Request(
    "http://localhost:8001/upload",
    data=body,
    headers={"Content-Type": ct}
)
try:
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
        print("UPLOAD OK:", data)
        fname = data["filename"]

        req2 = urllib.request.Request(
            f"http://localhost:8001/detect/{fname}",
            method="POST"
        )
        with urllib.request.urlopen(req2, timeout=60) as r2:
            det = json.loads(r2.read())
            print("DETECT OK")
            print("  Walls:   ", len(det["walls"]))
            print("  Rooms:   ", len(det["rooms"]))
            print("  Openings:", len(det["openings"]))
except Exception as e:
    import traceback
    print("ERROR:", e)
    traceback.print_exc()
