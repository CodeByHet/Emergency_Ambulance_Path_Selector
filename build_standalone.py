"""
build_standalone.py - make a single HTML file that works without Python.

    python build_standalone.py

Writes dist/ambulance_route_selector.html. Double-click it to open it in any
browser. It runs the JavaScript copy of the engine, which gives exactly the
same steps as engine.py. Handy for a demo machine without Python installed.
"""

import os

from app import BASE, render_page

out_dir = os.path.join(BASE, "dist")
os.makedirs(out_dir, exist_ok=True)
out = os.path.join(out_dir, "ambulance_route_selector.html")
with open(out, "w", encoding="utf-8") as f:
    f.write(render_page(server=False))
print("Wrote", out)
