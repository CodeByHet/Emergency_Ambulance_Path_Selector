"""
Emergency Ambulance Route Selector
DAA Assignment - Dijkstra's Shortest Path Algorithm

The city is modelled as a weighted graph:
    vertices = road junctions + hospitals
    edges    = roads between them
    weight   = travel time in minutes = (road length / speed) * 60,
               where speed depends on the traffic level on that road.

The ambulance starts at point A and must reach hospital B along the
minimum-cost (fastest) path. Dijkstra's algorithm is implemented from
scratch with a binary min-heap (heapq), and the result is drawn on a real
city map with folium (OpenStreetMap tiles).

This is the console version. For the interactive app run:  python app.py

Usage:
    python ambulance_route.py                         # default: GOTA -> ZYDUS
    python ambulance_route.py --src GOTA --dst VSH
    python ambulance_route.py --src GOTA --nearest    # pick nearest hospital
    python ambulance_route.py --list                  # show all node ids
    python ambulance_route.py --scenario negative-road     # Dijkstra fails -> Bellman-Ford
    python ambulance_route.py --scenario negative-cycle    # no shortest path exists
"""

import argparse
import heapq
import math

# ---------------------------------------------------------------------------
# 1. CITY DATA  (shared with the web app, edit city_data.json to change it)
# ---------------------------------------------------------------------------
import json
import os

with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "city_data.json"), encoding="utf-8") as _f:
    _DATA = json.load(_f)

# id: (display name, latitude, longitude, type)
NODES = {n["id"]: (n["name"], n["lat"], n["lon"], n["type"]) for n in _DATA["nodes"]}
# Average ambulance speed (km/h) for each traffic level
SPEED = _DATA["speeds_kmph"]
# Roads: (u, v, traffic level, one-way?, fixed cost or None)
ROADS = [(r["from"], r["to"], r["traffic"], r.get("oneway", False), r.get("cost")) for r in _DATA["roads"]]
# Teaching scenarios: {id: {"roads": {"U~V": {"oneway": bool, "cost": number}}, ...}}
SCENARIOS = {s["id"]: s for s in _DATA.get("scenarios", [])}
ROAD_FACTOR = _DATA["road_factor"]  # real roads are ~30% longer than the straight line


# ---------------------------------------------------------------------------
# 2. HELPERS: distance and graph construction
# ---------------------------------------------------------------------------
def haversine_km(lat1, lon1, lat2, lon2):
    """Great-circle distance between two lat/lng points, in km."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def build_graph(nodes, roads, road_overrides=None):
    """Adjacency list: graph[u] = [(v, cost_minutes, km, traffic), ...]"""
    road_overrides = road_overrides or {}
    graph = {n: [] for n in nodes}
    for u, v, traffic, oneway, cost in roads:
        ro = road_overrides.get(f"{u}~{v}", {})
        oneway, cost = ro.get("oneway", oneway), ro.get("cost", cost)
        _, la1, lo1, _ = nodes[u]
        _, la2, lo2, _ = nodes[v]
        km = round(haversine_km(la1, lo1, la2, lo2) * ROAD_FACTOR, 3)
        minutes = float(cost) if cost is not None else km / SPEED[traffic] * 60
        graph[u].append((v, minutes, km, traffic))
        if not oneway:
            graph[v].append((u, minutes, km, traffic))  # two-way road
    return graph


def negative_edges(graph):
    """Dijkstra is only correct when no edge is negative, so check first."""
    return [(u, v, w) for u in graph for v, w, _, _ in graph[u] if w < 0]


# ---------------------------------------------------------------------------
# 3. DIJKSTRA'S ALGORITHM (from scratch, min-heap version)
# ---------------------------------------------------------------------------
def dijkstra(graph, src, verbose=False):
    """
    Returns (dist, parent).
    dist[v]   = minimum travel time from src to v
    parent[v] = previous node on that best path (for reconstruction)
    """
    dist = {v: math.inf for v in graph}
    parent = {v: None for v in graph}
    visited = set()
    dist[src] = 0.0
    pq = [(0.0, src)]  # (distance so far, node)
    step = 0

    while pq:
        d, u = heapq.heappop(pq)       # node with smallest tentative distance
        if u in visited:               # stale heap entry, skip it
            continue
        visited.add(u)                 # u's distance is now final
        step += 1
        if verbose:
            print(f"Step {step:2}: finalize {u:<8} dist = {d:6.2f} min")

        for v, w, _, _ in graph[u]:    # relax every outgoing edge
            if v not in visited and d + w < dist[v]:
                if verbose:
                    old = "inf" if dist[v] == math.inf else f"{dist[v]:.2f}"
                    print(f"          relax {u}->{v:<8} {old:>6} -> {d + w:6.2f}")
                dist[v] = d + w
                parent[v] = u
                heapq.heappush(pq, (dist[v], v))
    return dist, parent


# ---------------------------------------------------------------------------
# 3b. BELLMAN-FORD (works with negative edges, detects negative cycles)
# ---------------------------------------------------------------------------
def bellman_ford(graph, src, verbose=False):
    """
    Relax every edge V-1 times. If an edge can still be relaxed after that,
    a negative cycle is reachable and there is no shortest path.
    Returns (dist, parent, cycle) where cycle is None or a list of nodes.
    Time O(V * E).
    """
    nodes = list(graph)
    dist = {v: math.inf for v in nodes}
    parent = {v: None for v in nodes}
    dist[src] = 0.0
    edges = [(u, v, w) for u in nodes for v, w, _, _ in graph[u]]

    for p in range(1, len(nodes)):
        changed = 0
        for u, v, w in edges:
            if dist[u] != math.inf and dist[u] + w < dist[v]:
                dist[v] = dist[u] + w
                parent[v] = u
                changed += 1
        if verbose:
            print(f"Pass {p:2}: {changed} improvements")
        if changed == 0:
            if verbose:
                print("         nothing changed, stop early")
            break

    for u, v, w in edges:                       # one extra check
        if dist[u] != math.inf and dist[u] + w < dist[v]:
            par = dict(parent)
            par[v] = u
            x = v
            for _ in range(len(nodes)):         # walk back into the cycle
                x = par[x]
            cycle, y = [x], par[x]
            while y != x:
                cycle.append(y)
                y = par[y]
            return dist, parent, cycle[::-1]
    return dist, parent, None


def reconstruct_path(parent, src, dst):
    """Walk parent pointers back from dst to src."""
    path, cur = [], dst
    while cur is not None:
        path.append(cur)
        cur = parent[cur]
    path.reverse()
    return path if path and path[0] == src else []


def nearest_hospital(dist):
    hospitals = [n for n, info in NODES.items() if info[3] == "hospital"]
    return min(hospitals, key=lambda h: dist[h])


# ---------------------------------------------------------------------------
# 4. BRUTE-FORCE CHECK: list every possible route (proves multiple paths
#    exist and that Dijkstra really picked the cheapest one)
# ---------------------------------------------------------------------------
def all_simple_paths(graph, src, dst):
    results = []

    def dfs(u, path, cost, seen):
        if u == dst:
            results.append((cost, list(path)))
            return
        for v, w, _, _ in graph[u]:
            if v not in seen:
                seen.add(v)
                path.append(v)
                dfs(v, path, cost + w, seen)
                path.pop()
                seen.remove(v)

    dfs(src, [src], 0.0, {src})
    return sorted(results)


def path_km(graph, path):
    total = 0.0
    for a, b in zip(path, path[1:]):
        total += next(km for v, _, km, _ in graph[a] if v == b)
    return total


# ---------------------------------------------------------------------------
# 5. MAP VISUALISATION
# ---------------------------------------------------------------------------
TRAFFIC_COLOR = {"low": "#2e7d32", "medium": "#f9a825", "high": "#c62828"}


def draw_map(graph, path, src, dst, alternatives, out_file):
    import folium

    lats = [NODES[n][1] for n in NODES]
    lons = [NODES[n][2] for n in NODES]
    m = folium.Map(location=[sum(lats) / len(lats), sum(lons) / len(lons)],
                   zoom_start=13, tiles="OpenStreetMap")

    # All roads, coloured by traffic, with cost in the tooltip
    drawn = set()
    for u in graph:
        for v, w, km, traffic in graph[u]:
            key = tuple(sorted((u, v)))
            if key in drawn:
                continue
            drawn.add(key)
            folium.PolyLine(
                [(NODES[u][1], NODES[u][2]), (NODES[v][1], NODES[v][2])],
                color="#1c2430" if w < 0 else TRAFFIC_COLOR[traffic], weight=4, opacity=0.55,
                dash_array="6 6" if w < 0 else None,
                tooltip=f"{NODES[u][0]} - {NODES[v][0]}: {km:.2f} km, "
                        f"{traffic} traffic, {w:.1f} min",
            ).add_to(m)

    # Next-best alternative routes, dashed grey
    for cost, alt in alternatives:
        folium.PolyLine([(NODES[n][1], NODES[n][2]) for n in alt],
                        color="#555", weight=3, dash_array="8 8", opacity=0.8,
                        tooltip=f"Alternative route: {cost:.1f} min").add_to(m)

    # The chosen shortest path, thick blue
    folium.PolyLine([(NODES[n][1], NODES[n][2]) for n in path],
                    color="#1565c0", weight=8, opacity=0.95,
                    tooltip="Shortest path").add_to(m)

    # Markers
    for n, (name, lat, lon, kind) in NODES.items():
        if n == src:
            folium.Marker([lat, lon], tooltip=f"A: Ambulance at {name}",
                          icon=folium.Icon(color="blue", icon="ambulance", prefix="fa")).add_to(m)
        elif kind == "hospital":
            color = "red" if n == dst else "lightred"
            label = "B: " if n == dst else ""
            folium.Marker([lat, lon], tooltip=f"{label}{name}",
                          icon=folium.Icon(color=color, icon="plus-square", prefix="fa")).add_to(m)
        else:
            folium.CircleMarker([lat, lon], radius=4, color="#333", fill=True,
                                fill_opacity=1, tooltip=name).add_to(m)

    legend = """
    <div style="position:fixed;bottom:24px;left:24px;z-index:9999;background:#fff;
         padding:10px 14px;border:1px solid #999;border-radius:6px;font:13px sans-serif">
      <b>Legend</b><br>
      <span style="color:#1565c0">&#9644;&#9644;</span> Shortest path<br>
      <span style="color:#555">- - -</span> Alternative routes<br>
      <span style="color:#2e7d32">&#9644;</span> Low traffic &nbsp;
      <span style="color:#f9a825">&#9644;</span> Medium &nbsp;
      <span style="color:#c62828">&#9644;</span> High
    </div>"""
    m.get_root().html.add_child(folium.Element(legend))
    m.save(out_file)


# ---------------------------------------------------------------------------
# 6. MAIN
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Emergency Ambulance Route Selector")
    ap.add_argument("--src", default="GOTA", help="ambulance start node id")
    ap.add_argument("--dst", default="ZYDUS", help="destination hospital id")
    ap.add_argument("--nearest", action="store_true", help="go to nearest hospital")
    ap.add_argument("--list", action="store_true", help="list node ids and exit")
    ap.add_argument("--scenario", default="normal", choices=sorted(SCENARIOS) or ["normal"],
                    help="teaching scenario from city_data.json")
    ap.add_argument("--out", default="ambulance_route_map.html")
    args = ap.parse_args()

    if args.list:
        for n, (name, _, _, kind) in NODES.items():
            print(f"{n:<8} {kind:<9} {name}")
        return

    graph = build_graph(NODES, ROADS, SCENARIOS.get(args.scenario, {}).get("roads"))
    src = args.src.upper()
    if src not in graph:
        raise SystemExit(f"Unknown start node {src}. Use --list.")

    # Dijkstra is only correct when every edge cost is >= 0. Check first.
    neg = negative_edges(graph)
    if neg:
        print("=" * 60)
        print("NEGATIVE EDGES FOUND -> using Bellman-Ford instead of Dijkstra")
        print("=" * 60)
        for u, v, w in neg:
            print(f"  {NODES[u][0]} -> {NODES[v][0]}: {w:.2f} min")
        print("Dijkstra marks a place final when it leaves the queue and never")
        print("revisits it, so a negative road found later can't fix it.\n")
        dist, parent, cycle = bellman_ford(graph, src, verbose=True)
        dj_dist, dj_parent = dijkstra(graph, src)
        if cycle:
            loop = " -> ".join(NODES[c][0] for c in cycle + cycle[:1])
            print(f"\nNegative cycle: {loop}")
            print("Every lap lowers the cost, so there is NO shortest path.")
            return
    else:
        print("=" * 60)
        print("DIJKSTRA TRACE")
        print("=" * 60)
        dist, parent = dijkstra(graph, src, verbose=True)

    dst = nearest_hospital(dist) if args.nearest else args.dst.upper()
    if dst not in graph:
        raise SystemExit(f"Unknown destination {dst}. Use --list.")

    path = reconstruct_path(parent, src, dst)
    if not path:
        raise SystemExit(f"No route from {src} to {dst}.")

    print("\n" + "=" * 60)
    print("RESULT")
    print("=" * 60)
    print(f"From : {NODES[src][0]}")
    print(f"To   : {NODES[dst][0]}" + ("  (nearest hospital)" if args.nearest else ""))
    print("Route: " + " -> ".join(NODES[n][0] for n in path))
    print(f"Time : {dist[dst]:.2f} min   Distance: {path_km(graph, path):.2f} km")
    if neg:
        dj_path = reconstruct_path(dj_parent, src, dst)
        print(f"Dijkstra would have said {dj_dist[dst]:.2f} min via " + " -> ".join(dj_path)
              + ("  (WRONG)" if abs(dj_dist[dst] - dist[dst]) > 1e-9 else "  (right by luck)"))

    routes = all_simple_paths(graph, src, dst)
    print(f"\nTotal possible routes found by brute force: {len(routes)}")
    print("Cheapest 5:")
    for cost, p in routes[:5]:
        print(f"  {cost:6.2f} min  {path_km(graph, p):5.2f} km  " + " -> ".join(p))
    algo = "Bellman-Ford" if neg else "Dijkstra"
    assert abs(routes[0][0] - dist[dst]) < 1e-9, f"{algo} disagrees with brute force!"
    print(f"Check: {algo}'s answer matches the brute-force minimum. OK")

    shortest_km = min(routes, key=lambda r: path_km(graph, r[1]))
    if shortest_km[1] != path:
        print(f"\nNote: the shortest-DISTANCE route ({path_km(graph, shortest_km[1]):.2f} km, "
              f"{shortest_km[0]:.2f} min) is slower because of traffic.")

    if args.nearest:
        print("\nTravel time to every hospital:")
        for h in sorted((n for n in NODES if NODES[n][3] == "hospital"), key=dist.get):
            print(f"  {NODES[h][0]:<28} {dist[h]:6.2f} min")

    draw_map(graph, path, src, dst, routes[1:3], args.out)
    print(f"\nMap saved to {args.out} (open it in a browser)")


if __name__ == "__main__":
    main()
