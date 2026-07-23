import urllib.request
import json
import os
import traceback

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
    "http://localhost:8001/upload-and-detect",
    data=body,
    headers={"Content-Type": ct}
)

try:
    with urllib.request.urlopen(req, timeout=30) as resp:
        res = json.loads(resp.read())
        print("STATUS:", resp.status)
        print("UPLOAD KEYS:", list(res.get("upload", {}).keys()))
        print("DETECTION KEYS:", list(res.get("detection", {}).keys()) if res.get("detection") else "None")
        if "detection" in res and res["detection"]:
            print("Walls:", len(res["detection"]["walls"]))
            print("Rooms:", len(res["detection"]["rooms"]))
            print("Openings:", len(res["detection"]["openings"]))
        else:
            print("No detection results. Error/Warning:", res.get("error"), res.get("warning"))
except Exception as e:
    print("ERROR:", e)
    traceback.print_exc()
