# Emergency Ambulance Route Selector
DAA assignment: Dijkstra's shortest path on a city road network.

An ambulance is at point **A**. The user picks a hospital **B**, or asks for the
nearest one. The app finds the minimum-cost route with Dijkstra's algorithm. It
then replays every decision the algorithm made, so you can see why each more
expensive route was ignored.

Roads normally cost travel time, which is never negative. A **Mode** menu adds
two teaching scenarios with a negative road, to show why Dijkstra needs
non-negative weights and how Bellman-Ford handles them.

## Run it

```bash
pip install flask
python app.py            # open http://127.0.0.1:5000
```

No Python on the demo machine? Run `python build_standalone.py` once, then
double-click `dist/ambulance_route_selector.html`. It uses a JavaScript copy of
the engine that produces exactly the same steps.

The console version, `python ambulance_route.py`, prints the trace and also
draws a folium map with real OpenStreetMap tiles.

## Project structure

| File | What it does |
|---|---|
| `city_data.json` | Places (junctions and hospitals with lat/lon), roads, traffic level per road, speed per traffic level |
| `engine.py` | Builds the graph, runs Dijkstra or Bellman-Ford and records every step, brute-forces all routes for comparison |
| `app.py` | Flask server: serves the page, `/api/route` and `/api/scenarios` |
| `tests/test_engine.py` | pytest suite (`python -m pytest -q`) |
| `tests/parity.py` | Checks that the JavaScript engine gives exactly the same output as `engine.py` (needs Node.js) |
| `templates/index.html` | The UI: SVG city map, playback controls, explanations, pseudocode, priority queue, distance table, route comparison, ambulance animation |
| `build_standalone.py` | Builds a single offline HTML file |
| `ambulance_route.py` | Console version with a folium map |

## How it works, step by step

1. **Model the city as a graph.** Junctions and hospitals are vertices. Roads are edges, two-way unless a scenario marks them one-way.
2. **Give every edge a cost.** cost = length (km) × 60 ÷ speed (km/h). Speed depends on traffic: low 45, medium 28, heavy 14. A closed road is left out of the graph. Length is the Haversine distance × 1.3.
3. **Check the weights.** Any negative edge switches to Bellman-Ford (see below). Otherwise, **run Dijkstra with a min-heap.** Every action is recorded as an event:
   - `pop`: the cheapest place leaves the queue and becomes final
   - `relax`: a road u→v is checked, with one of three results:
     - `update`: d(u) + w < dist[v], so keep it, or replace a more expensive route
     - `reject`: d(u) + w ≥ dist[v], so ignore the road
     - `final`: v is already final, so skip it
   - `stale`: an old heap entry for a place that was already finalized
   - `found`: B is finalized, so stop early
4. **Rebuild the route** by following `via[]` (parent) links back from B to A.
5. **Explain the losers.** All simple routes are listed by DFS. For each runner-up, the app finds the first road where it leaves Dijkstra's shortest-path tree, then points to the exact step where that road was ignored, replaced, or never explored.
6. **Verify.** The brute-force minimum must equal Dijkstra's answer, and the code asserts this.
7. **Animate.** The ambulance drives the route. It spends time on each road in proportion to that road's cost, so it visibly slows down in heavy traffic.

## Why a more expensive path is ignored (the key idea)

When a place leaves the priority queue, it is the cheapest unfinished place. Any
other route to it would have to pass through some place that already costs more.
Since no road has a negative cost, that route can only get more expensive. So the
popped cost is final.

After that point, any road that offers a higher cost to an already-reached place
is rejected. A route that was only the best one so far gets replaced the moment
a cheaper one appears.

## Negative weights

Dijkstra is only correct when every edge cost is 0 or more. A place becomes
final when it leaves the queue and is never looked at again. With a negative
road, a route found later can be cheaper, and Dijkstra misses it.

So the engine checks the weights first:

- **No negative edge:** it runs Dijkstra.
- **Any negative edge:** it runs **Bellman-Ford**. Bellman-Ford relaxes every
  road V − 1 times, because a shortest route never needs more than V − 1 roads.
  It stops early when a pass changes nothing.
- **Negative cycle:** if a road can still lower a cost after those passes, there
  is a negative cycle and no shortest path exists.

A negative **two-way** road is always a negative cycle (u → v → u), so a
negative road has to be one-way.

**Worked example (Mode: Negative road).** Science City → Sola Bridge is made a
one-way road with cost −6 min.

| | Answer | Route |
|---|---|---|
| Dijkstra (wrong) | 19.46 min | Gota → Science City → Thaltej → Zydus |
| Bellman-Ford (correct) | 17.67 min | Gota → Science City → Sola Bridge → Drive-in → Bodakdev → Thaltej → Zydus |

Dijkstra finalizes Sola Bridge at 7.71 min (via Gota). When it later checks
Science City → Sola Bridge (8.81 − 6.00 = 2.81 min), Sola Bridge is already
final, so the cheaper route is skipped. The app has a "Show where Dijkstra went
wrong" button that jumps to exactly that step.

**Mode: Negative cycle.** Science City ↔ Sola Bridge costs −6 min both ways.
Each lap adds −12 min. Bellman-Ford reports that no shortest path exists, while
Dijkstra still prints an answer (12.36 min) that means nothing.

## Complexity

- Dijkstra: O((V + E) log V) time with a binary heap, O(V + E) space
- Bellman-Ford: O(V · E) time, O(V) extra space
- The brute-force check is exponential. It is only there to verify the answer on this small map.

## Tests

```bash
pip install pytest
python -m pytest -q        # engine and API tests
python tests/parity.py     # Python vs JavaScript engine, about 1,300 scenarios
```

## Things to try in the demo

- **Gota → Zydus:** the shortest-distance route (Sola Bridge → Thaltej, 9.98 km) loses to a longer but faster route because of heavy traffic on the flyover.
- **Close the Gota–Sola Bridge road** (click it until it shows "closed") and watch the route change.
- **Pick "Nearest hospital":** Dijkstra stops at the first hospital that leaves the queue.
- **Close every road into a hospital** to see the "no route" case.
- **Mode: Negative road.** Compare Dijkstra with Bellman-Ford, then click "Show where Dijkstra went wrong".
- **Mode: Negative cycle.** Watch Bellman-Ford run all 18 passes and then find the cycle.
- <img width="2666" height="1316" alt="image" src="https://github.com/user-attachments/assets/efd9eab2-ae79-424f-8cc9-228a5d902057" />

