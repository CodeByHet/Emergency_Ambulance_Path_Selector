"""
app.py - Flask web server for the Emergency Ambulance Route Selector.

Run:
    pip install flask
    python app.py
Then open http://127.0.0.1:5000 in a browser.

Routes
    GET  /                 the interactive map + step-by-step simulation
    GET  /api/graph        the city graph (places, roads, km, traffic)
    GET  /api/scenarios    the three teaching scenarios (normal, negative road, negative cycle)
    POST /api/route        find a route   body: {"src": "GOTA", "dst": "ZYDUS" | "NEAREST",
                                                  "traffic": {"SOLA~THALTEJ": "closed", ...},
                                                  "scenario": "normal" | "negative-road" | "negative-cycle",
                                                  "algorithm": "auto" | "dijkstra" | "bellman-ford"}
    GET  /api/route?src=GOTA&dst=ZYDUS&scenario=negative-road   same thing, for testing in a browser
"""

import json
import os

from flask import Flask, Response, jsonify, request

from engine import ALGORITHMS, TRAFFIC_LEVELS, find_route, load_city

BASE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(BASE, "templates", "index.html")

app = Flask(__name__)
CITY = load_city()
EDGE_IDS = {e["id"] for e in CITY["edges"]}


def render_page(server=True):
    """Insert the city graph into the page and wrap it in a full HTML document."""
    with open(TEMPLATE, encoding="utf-8") as f:
        body = f.read()
    data = dict(CITY, server=server)
    body = body.replace("__CITY_DATA__", json.dumps(data).replace("</", "<\\/"))
    return (
        "<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1, viewport-fit=cover\">\n"
        "</head>\n<body>\n" + body + "\n</body>\n</html>\n"
    )


@app.get("/")
def index():
    return Response(render_page(server=True), mimetype="text/html")


@app.get("/api/graph")
def graph():
    return jsonify(CITY)


@app.get("/api/scenarios")
def scenarios():
    return jsonify(CITY["scenarios"])


@app.route("/api/route", methods=["GET", "POST"])
def route():
    if request.method == "POST":
        body = request.get_json(silent=True) or {}
    else:
        body = {"src": request.args.get("src", ""), "dst": request.args.get("dst", "NEAREST"), "traffic": {},
                "scenario": request.args.get("scenario", "normal"),
                "algorithm": request.args.get("algorithm", "auto")}

    src = str(body.get("src", "")).upper()
    dst = str(body.get("dst", "")).upper()
    scenario = str(body.get("scenario") or "normal")
    algorithm = str(body.get("algorithm") or "auto")
    traffic = body.get("traffic") or {}
    if not isinstance(traffic, dict):
        return jsonify(error="traffic must be an object like {\"SOLA~THALTEJ\": \"closed\"}"), 400
    overrides = {k: v for k, v in traffic.items() if k in EDGE_IDS and v in TRAFFIC_LEVELS}
    if algorithm not in ALGORITHMS:
        return jsonify(error=f"Unknown algorithm: {algorithm}. Use one of: {', '.join(ALGORITHMS)}"), 400

    try:
        return jsonify(find_route(CITY, src, dst, overrides, scenario=scenario, algorithm=algorithm))
    except ValueError as err:
        return jsonify(error=str(err)), 400


if __name__ == "__main__":
    app.run(debug=True)
