import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CAD_BACKEND = os.path.abspath(os.path.join(HERE, "..", ".."))
APP_BACKEND = os.path.abspath(os.path.join(CAD_BACKEND, "..", "..", "backend"))
for p in (CAD_BACKEND, APP_BACKEND):
    if p not in sys.path:
        sys.path.insert(0, p)
