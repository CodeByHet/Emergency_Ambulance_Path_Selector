"""
Python vs JavaScript engine parity check.

Extracts the JS engine from templates/index.html, runs it in Node for many
scenarios and compares the JSON with engine.py exactly (ignoring "engine").

Run from the project folder:   python tests/parity.py
Needs Node.js on PATH.
"""
import json
import os
import random
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import ALGORITHMS, find_route, load_city  # noqa: E402


def main():
    city = load_city()
    html = open(os.path.join(ROOT, "templates", "index.html"), encoding="utf-8").read()
    engine_js = html[html.index("// ENGINE START"):html.index("// ENGINE END")]

    ids = [n["id"] for n in city["nodes"]]
    hospitals = [n["id"] for n in city["nodes"] if n["type"] == "hospital"]
    edge_ids = [e["id"] for e in city["edges"]]
    scenarios = [s["id"] for s in city["scenarios"]]

    cases = []
    for sc in scenarios:
        for alg in ALGORITHMS:
            for s in ids:
                for d in hospitals + ["NEAREST"]:
                    if d != s:
                        cases.append([s, d, {}, sc, alg])
    rng = random.Random(42)
    for _ in range(300):
        traffic = {e: rng.choice(["low", "medium", "high", "closed"]) for e in rng.sample(edge_ids, rng.randint(1, 8))}
        s = rng.choice(ids)
        d = rng.choice([h for h in hospitals if h != s] + ["NEAREST"])
        cases.append([s, d, traffic, rng.choice(scenarios), rng.choice(ALGORITHMS)])

    script = (engine_js + "\nconst city = " + json.dumps(city) + ";\nconst cases = " + json.dumps(cases) + ";\n"
              "process.stdout.write(JSON.stringify(cases.map(([s, d, t, sc, a]) => "
              "Engine.findRoute(city, s, d, t, { scenario: sc, algorithm: a }))));\n")
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "parity.js")
        with open(path, "w", encoding="utf-8") as f:
            f.write(script)
        js_results = json.loads(subprocess.check_output(["node", path], cwd=tmp))

    mismatches = 0
    for (s, d, t, sc, a), js in zip(cases, js_results):
        py = json.loads(json.dumps(find_route(city, s, d, t, scenario=sc, algorithm=a)))
        py.pop("engine")
        js.pop("engine")
        if py != js:
            mismatches += 1
            if mismatches <= 3:
                keys = [k for k in py if py[k] != js.get(k)]
                print(f"MISMATCH {s}->{d} scenario={sc} algorithm={a} traffic={t}: {keys}")
    print(f"{len(cases)} cases compared, {mismatches} mismatches")
    return 1 if mismatches else 0


if __name__ == "__main__":
    sys.exit(main())
