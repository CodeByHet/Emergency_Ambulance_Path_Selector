"""
engine.py - the algorithm side of the Emergency Ambulance Route Selector.

Everything the web app shows comes from here:
  * load_city()           reads city_data.json and turns it into a weighted graph
  * dijkstra_trace()      runs Dijkstra and records EVERY decision it makes
  * bellman_ford_trace()  runs Bellman-Ford the same way (used when a road has a
                          negative cost) and detects negative cycles
  * all_routes()          brute-force list of every simple route A -> B, used to
                          show why the more expensive routes lose
  * find_route()          picks the right algorithm and ties it all together

Edge weight (cost) = travel time in minutes
                   = road length (km) / speed for its traffic level (km/h) * 60
A scenario can also give a road a fixed cost (which may be negative) and make
it one-way. That is the "negative-weight lab": real travel time is never
negative, but it shows exactly why Dijkstra needs non-negative weights.
"""

import heapq
import json
import math
import os

DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "city_data.json")
TRAFFIC_LEVELS = ["low", "medium", "high", "closed"]
ALGORITHMS = ["auto", "dijkstra", "bellman-ford"]


# ---------------------------------------------------------------------------
# 1. Load the city and build the graph
# ---------------------------------------------------------------------------
def haversine_km(lat1, lon1, lat2, lon2):
    """Great-circle distance between two points on Earth, in km."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def edge_id(u, v):
    return f"{u}~{v}"


def load_city(path=DATA_FILE):
    """Read city_data.json and attach a road length (km) to every road."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    nodes = {n["id"]: n for n in data["nodes"]}
    edges = []
    for r in data["roads"]:
        a, b = nodes[r["from"]], nodes[r["to"]]
        km = haversine_km(a["lat"], a["lon"], b["lat"], b["lon"]) * data["road_factor"]
        edges.append({
            "id": edge_id(r["from"], r["to"]),
            "u": r["from"],
            "v": r["to"],
            "km": round(km, 3),          # rounded so Python and JS see the same number
            "traffic": r["traffic"],
            "oneway": bool(r.get("oneway", False)),
            "cost": r.get("cost"),       # fixed cost in minutes, or None = use traffic
        })
    return {
        "city": data["city"],
        "speeds": data["speeds_kmph"],
        "nodes": data["nodes"],
        "edges": edges,
        "scenarios": data.get("scenarios", []),
        "map": data["map"],
    }


def scenario_roads(city, scenario):
    """Road changes for a scenario id ({} for None / "normal")."""
    if scenario in (None, ""):
        return {}
    for s in city["scenarios"]:
        if s["id"] == scenario:
            return s["roads"]
    raise ValueError(f"Unknown scenario: {scenario}")


def minutes(km, traffic, speeds):
    """Cost of one road from its traffic level. A closed road has no cost."""
    if traffic == "closed":
        return None
    return km / speeds[traffic] * 60


def build_adjacency(city, traffic_overrides=None, road_overrides=None):
    """
    Adjacency list: adj[u] = [(v, cost_minutes, km, edge_id), ...]
    traffic_overrides = {edge_id: "low"|"medium"|"high"|"closed"}  (clicked on the map)
    road_overrides    = {edge_id: {"oneway": bool, "cost": number}} (from a scenario)
    Order: roads in the order of city_data.json, forward direction first.
    """
    traffic_overrides = traffic_overrides or {}
    road_overrides = road_overrides or {}
    adj = {n["id"]: [] for n in city["nodes"]}
    for e in city["edges"]:
        ro = road_overrides.get(e["id"], {})
        traffic = traffic_overrides.get(e["id"], e["traffic"])
        if traffic == "closed":
            continue
        cost = ro.get("cost", e["cost"])
        oneway = ro.get("oneway", e["oneway"])
        w = float(cost) if cost is not None else minutes(e["km"], traffic, city["speeds"])
        adj[e["u"]].append((e["v"], w, e["km"], e["id"]))
        if not oneway:
            adj[e["v"]].append((e["u"], w, e["km"], e["id"]))   # two-way road
    return adj


def negative_edges(adj):
    """Every directed edge with a negative cost."""
    return [{"u": u, "v": v, "w": w, "edge": eid}
            for u in adj for (v, w, _km, eid) in adj[u] if w < 0]


# ---------------------------------------------------------------------------
# 2. Dijkstra's algorithm with a full event trace
# ---------------------------------------------------------------------------
def dijkstra_trace(adj, src, targets):
    """
    Standard Dijkstra with a binary min-heap (lazy deletion).
    Only correct when every edge cost is >= 0.

    Stops as soon as one of `targets` is taken out of the queue: at that
    moment its cost is final, so nothing explored later could beat it.

    Returns (events, dist, parent, reached_target).
    Events:
      init   - source gets cost 0, everything else infinity
      pop    - smallest entry leaves the queue and becomes final
      stale  - an old, more expensive queue entry for an already-final node
      found  - the popped node is a target -> stop
      relax  - one road u->v is checked; result is
                 "update"  d(u)+w beats dist[v]  -> keep it
                 "reject"  d(u)+w does not beat dist[v] -> ignore road
                 "final"   v is already final -> never revisited
                           (with a negative road this is where Dijkstra goes wrong)
      empty  - queue ran out before reaching a target
    """
    INF = math.inf
    dist = {v: INF for v in adj}
    parent = {v: None for v in adj}
    final = set()

    dist[src] = 0.0
    heap = [(0.0, src)]
    events = [{"type": "init", "node": src}]
    reached = None

    while heap:
        d, u = heapq.heappop(heap)

        if u in final:                                   # lazy deletion
            events.append({"type": "stale", "node": u, "d": d, "final": dist[u]})
            continue

        final.add(u)
        events.append({"type": "pop", "node": u, "d": d})

        if u in targets:
            events.append({"type": "found", "node": u, "d": d})
            reached = u
            break

        for v, w, _km, eid in adj[u]:
            new = d + w
            old = dist[v]
            if v in final:
                result = "final"
            elif new < old:
                result = "update"
            else:
                result = "reject"
            events.append({
                "type": "relax", "u": u, "v": v, "edge": eid, "w": w, "du": d,
                "old": None if old == INF else old, "new": new,
                "oldParent": parent[v], "result": result,
            })
            if result == "update":
                dist[v] = new
                parent[v] = u
                heapq.heappush(heap, (new, v))
    else:
        events.append({"type": "empty"})

    return events, dist, parent, reached


# ---------------------------------------------------------------------------
# 3. Bellman-Ford with a full event trace (handles negative costs)
# ---------------------------------------------------------------------------
def bellman_ford_trace(adj, src, targets):
    """
    Bellman-Ford: check every road, V-1 times. A shortest route uses at most
    V-1 roads, so after pass k every route with k roads has been found.

    Edge order (fixed, so the trace is deterministic): places in the order of
    city_data.json, and for each place its roads in adjacency order. Roads
    that start at a place still at infinity are skipped (nothing to relax).

    After V-1 passes one more check runs: if any road can STILL lower a cost,
    a negative cycle is reachable and every place reachable from it has no
    shortest path (its cost can drop forever).

    Returns (events, dist, parent, cycle, affected, reached).
    Events: init, bf_pass, relax (result "update"|"reject"), bf_pass_done,
            early_exit, cycle_check, cycle_found, done
    """
    INF = math.inf
    order = list(adj)
    n = len(order)
    dist = {v: INF for v in order}
    parent = {v: None for v in order}
    dist[src] = 0.0
    edges = [(u, v, w, eid) for u in order for (v, w, _km, eid) in adj[u]]
    events = [{"type": "init", "node": src}]

    for p in range(1, n):
        events.append({"type": "bf_pass", "pass": p, "of": n - 1})
        changes = 0
        for u, v, w, eid in edges:
            if dist[u] == INF:
                continue
            du = dist[u]
            new = du + w
            old = dist[v]
            result = "update" if new < old else "reject"
            events.append({
                "type": "relax", "u": u, "v": v, "edge": eid, "w": w, "du": du,
                "old": None if old == INF else old, "new": new,
                "oldParent": parent[v], "result": result, "pass": p,
            })
            if result == "update":
                dist[v] = new
                parent[v] = u
                changes += 1
        events.append({"type": "bf_pass_done", "pass": p, "changes": changes})
        if changes == 0:
            events.append({"type": "early_exit", "pass": p})
            break

    events.append({"type": "cycle_check"})
    relaxable = [(u, v) for u, v, w, _ in edges if dist[u] != INF and dist[u] + w < dist[v]]
    cycle, affected = None, []
    if relaxable:
        u0, v0 = relaxable[0]
        par = dict(parent)
        par[v0] = u0
        x = v0
        for _ in range(n):                 # walk back n times -> lands inside the cycle
            x = par[x]
        loop = [x]
        y = par[x]
        while y != x:
            loop.append(y)
            y = par[y]
        loop.reverse()                     # parent pointers run backwards
        first = min(range(len(loop)), key=lambda i: order.index(loop[i]))
        cycle = loop[first:] + loop[:first]
        cost = 0.0
        for a, b in zip(cycle, cycle[1:] + cycle[:1]):
            cost += min(w for (v, w, _k, _e) in adj[a] if v == b)
        start = [v for _, v in relaxable] + cycle
        seen, stack = set(start), list(start)
        while stack:
            a = stack.pop()
            for b, _w, _k, _e in adj[a]:
                if b not in seen:
                    seen.add(b)
                    stack.append(b)
        affected = [v for v in order if v in seen]
        events.append({"type": "cycle_found", "cycle": cycle, "u": u0, "v": v0,
                       "cost": cost, "affected": affected})

    aff = set(affected)
    if aff & set(targets):
        reached = None
    else:
        candidates = [t for t in order if t in targets and dist[t] != INF]
        reached = min(candidates, key=lambda t: (dist[t], order.index(t))) if candidates else None
    events.append({"type": "done", "node": reached, "d": dist[reached] if reached else None})
    return events, dist, parent, cycle, affected, reached


def reconstruct_path(parent, src, dst):
    path, cur = [], dst
    while cur is not None and len(path) <= len(parent):
        path.append(cur)
        cur = parent[cur]
    path.reverse()
    return path if path and path[0] == src else []


# ---------------------------------------------------------------------------
# 4. Brute force: every simple route, to compare against the algorithm
# ---------------------------------------------------------------------------
def all_routes(adj, src, dst, cap=20000):
    found = []

    def dfs(u, path, cost, km, seen):
        if len(found) >= cap:
            return
        if u == dst:
            found.append({"path": list(path), "cost": cost, "km": km})
            return
        for v, w, k, _ in adj[u]:
            if v not in seen:
                seen.add(v)
                path.append(v)
                dfs(v, path, cost + w, km + k, seen)
                path.pop()
                seen.remove(v)

    dfs(src, [src], 0.0, 0.0, {src})
    found.sort(key=lambda r: (r["cost"], r["path"]))
    return found


def path_km(adj, path):
    total = 0.0
    for a, b in zip(path, path[1:]):
        total += next(k for v, _w, k, _ in adj[a] if v == b)
    return total


# ---------------------------------------------------------------------------
# 5. One request from the app
# ---------------------------------------------------------------------------
def _fmt(x):
    return f"{x:.1f}".replace("-", "−")


def find_route(city, src, dst, traffic_overrides=None, alt_count=4, scenario=None, algorithm="auto"):
    """
    dst can be a hospital id or "NEAREST".
    algorithm: "auto" (Dijkstra unless a road has a negative cost, then
    Bellman-Ford), "dijkstra" (forced, flagged unreliable on a negative map)
    or "bellman-ford".
    Returns a JSON-ready dict with the trace, the chosen route, the best
    alternative routes and, on a negative map, both algorithms' answers.
    """
    names = {n["id"]: n["name"] for n in city["nodes"]}
    if src not in names:
        raise ValueError(f"Unknown start point: {src}")
    nearest = dst == "NEAREST"
    if not nearest and dst not in names:
        raise ValueError(f"Unknown destination: {dst}")
    if algorithm not in ALGORITHMS:
        raise ValueError(f"Unknown algorithm: {algorithm}. Use one of: {', '.join(ALGORITHMS)}")
    roads = scenario_roads(city, scenario)

    adj = build_adjacency(city, traffic_overrides, roads)
    if nearest:
        targets = {n["id"] for n in city["nodes"] if n["type"] == "hospital" and n["id"] != src}
    else:
        targets = {dst}

    neg = negative_edges(adj)
    use = "dijkstra" if algorithm == "dijkstra" or (algorithm == "auto" and not neg) else "bellman-ford"

    dj = bf = None
    if use == "dijkstra" or neg:
        dj = dijkstra_trace(adj, src, targets)
    if use == "bellman-ford" or neg:
        bf = bellman_ford_trace(adj, src, targets)

    if use == "dijkstra":
        events, dist, parent, reached = dj
        cycle, affected = None, []
    else:
        events, dist, parent, cycle, affected, reached = bf
    unreliable = bool(neg) and use == "dijkstra"
    path = reconstruct_path(parent, src, reached) if reached else []

    alternatives, total_routes, shortest_km = [], 0, None
    if reached:
        routes = all_routes(adj, src, reached)
        total_routes = len(routes)
        alternatives = [r for r in routes if r["path"] != path][:alt_count]
        if routes:
            shortest_km = min(routes, key=lambda r: (round(r["km"], 6), r["cost"]))
            if shortest_km["path"] != path and shortest_km not in alternatives:
                alternatives.append(shortest_km)
        if not unreliable:
            # sanity check: the algorithm must equal the brute-force minimum
            assert abs(routes[0]["cost"] - dist[reached]) < 1e-9

    dijkstra_check = bellman_check = None
    if neg:
        dj_events, dj_dist, dj_parent, dj_reached = dj
        bf_events, bf_dist, bf_parent, bf_cycle, bf_aff, bf_reached = bf
        dj_cost = dj_dist[dj_reached] if dj_reached else None
        bf_cost = bf_dist[bf_reached] if bf_reached else None
        wrong = (dj_reached != bf_reached) or (
            dj_cost is not None and bf_cost is not None and abs(dj_cost - bf_cost) > 1e-9)
        wrong_step = next((i for i, e in enumerate(dj_events)
                           if e["type"] == "relax" and e["result"] == "final" and e["new"] < e["old"]), None)
        dijkstra_check = {"cost": dj_cost, "dst": dj_reached,
                          "path": reconstruct_path(dj_parent, src, dj_reached) if dj_reached else [],
                          "wrong": wrong, "wrongStep": wrong_step}
        bellman_check = {"cost": bf_cost, "dst": bf_reached,
                         "path": reconstruct_path(bf_parent, src, bf_reached) if bf_reached else [],
                         "negativeCycle": bf_cycle}

    warning = None
    if neg:
        seen, listed = set(), []
        for e in neg:
            if e["edge"] not in seen:
                seen.add(e["edge"])
                listed.append(f"{names[e['u']]} → {names[e['v']]} ({_fmt(e['w'])} min)")
        roads_text = ", ".join(listed)
        target = names[dst] if not nearest else "the hospitals"
        bf_cycle = bellman_check["negativeCycle"]
        if use == "dijkstra":
            verdict = "is wrong" if dijkstra_check["wrong"] else "happens to be right here"
            warning = (f"Dijkstra was run on a map with a negative road: {roads_text}. "
                       f"Its answer {verdict}, because it never revisits a place once it is final.")
        elif bf_cycle and not reached:
            loop = " → ".join(names[c] for c in bf_cycle + bf_cycle[:1])
            cyc_cost = next(e["cost"] for e in events if e["type"] == "cycle_found")
            warning = (f"Negative cycle: {loop} adds up to {_fmt(cyc_cost)} min. Every lap lowers the cost, "
                       f"so there is no shortest path to {target}.")
        elif bf_cycle:
            loop = " → ".join(names[c] for c in bf_cycle + bf_cycle[:1])
            warning = (f"There is a negative cycle ({loop}), but it can't reach {names[reached]}, "
                       f"so the route there is still well defined.")
        else:
            warning = (f"This map has a road with a negative cost: {roads_text}. "
                       f"Dijkstra can't be trusted here, so Bellman-Ford was used.")

    def clean(x):
        return None if x == math.inf else x

    return {
        "engine": "python",
        "src": src,
        "dst": reached,
        "mode": "nearest" if nearest else "hospital",
        "requested": dst,
        "scenario": scenario or "normal",
        "algorithm": use,
        "events": events,
        "path": path,
        "cost": dist[reached] if reached else None,
        "km": path_km(adj, path) if path else None,
        "dist": {k: clean(v) for k, v in dist.items()},
        "parent": parent,
        "alternatives": alternatives,
        "totalRoutes": total_routes,
        "shortestKmPath": shortest_km["path"] if shortest_km else None,
        "negativeEdges": neg,
        "negativeCycle": cycle,
        "affected": affected,
        "unreliable": unreliable,
        "warning": warning,
        "dijkstraCheck": dijkstra_check,
        "bellmanFordCheck": bellman_check,
    }


if __name__ == "__main__":
    city = load_city()
    for sc in ("normal", "negative-road", "negative-cycle"):
        r = find_route(city, "GOTA", "ZYDUS", scenario=sc)
        print(f"[{sc}] algorithm={r['algorithm']}")
        if r["path"]:
            print("  Route:", " -> ".join(r["path"]), f"= {r['cost']:.2f} min, {r['km']:.2f} km")
        if r["warning"]:
            print("  " + r["warning"])
        if r["dijkstraCheck"]:
            d = r["dijkstraCheck"]
            print("  Dijkstra would say:", d["cost"] and round(d["cost"], 2), d["path"], "wrong" if d["wrong"] else "right")
