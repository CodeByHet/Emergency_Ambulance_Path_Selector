"""
Run from the project folder:   python -m pytest -q
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import build_adjacency, find_route, load_city  # noqa: E402

CITY = load_city()
IDS = [n["id"] for n in CITY["nodes"]]
HOSPITALS = [n["id"] for n in CITY["nodes"] if n["type"] == "hospital"]


def test_normal_map_gota_to_zydus():
    r = find_route(CITY, "GOTA", "ZYDUS")
    assert r["algorithm"] == "dijkstra"
    assert r["path"] == ["GOTA", "SCIENCE", "THALTEJ", "ZYDUS"]
    assert round(r["cost"], 2) == 19.46
    assert r["negativeEdges"] == [] and r["warning"] is None


@pytest.mark.parametrize("src", IDS)
def test_dijkstra_equals_bellman_ford_on_normal_map(src):
    for dst in HOSPITALS + ["NEAREST"]:
        if dst == src:
            continue
        dj = find_route(CITY, src, dst, algorithm="dijkstra")
        bf = find_route(CITY, src, dst, algorithm="bellman-ford")
        assert dj["dst"] == bf["dst"]
        assert dj["cost"] == pytest.approx(bf["cost"], abs=1e-9)
        assert bf["negativeCycle"] is None


def test_negative_road_dijkstra_wrong_bellman_ford_right():
    r = find_route(CITY, "GOTA", "ZYDUS", scenario="negative-road")
    assert r["algorithm"] == "bellman-ford"
    assert r["path"] == ["GOTA", "SCIENCE", "SOLA", "DRIVEIN", "BODAK", "THALTEJ", "ZYDUS"]
    assert round(r["cost"], 2) == 17.67
    assert r["negativeCycle"] is None

    check = r["dijkstraCheck"]
    assert check["wrong"] is True
    assert round(check["cost"], 2) == 19.46
    assert check["path"] == ["GOTA", "SCIENCE", "THALTEJ", "ZYDUS"]

    # wrongStep indexes the Dijkstra trace: the SCIENCE -> SOLA relax that is skipped
    forced = find_route(CITY, "GOTA", "ZYDUS", scenario="negative-road", algorithm="dijkstra")
    assert forced["unreliable"] is True
    ev = forced["events"][check["wrongStep"]]
    assert (ev["type"], ev["u"], ev["v"], ev["result"]) == ("relax", "SCIENCE", "SOLA", "final")
    assert round(ev["new"], 2) == 2.81 and round(ev["old"], 2) == 7.71


def test_negative_road_is_one_way():
    adj = build_adjacency(CITY, None, {"SCIENCE~SOLA": {"oneway": True, "cost": -6}})
    assert any(v == "SOLA" and w == -6 for v, w, _, _ in adj["SCIENCE"])
    assert not any(v == "SCIENCE" for v, *_ in adj["SOLA"])


def test_negative_cycle_scenario():
    r = find_route(CITY, "GOTA", "ZYDUS", scenario="negative-cycle")
    assert r["algorithm"] == "bellman-ford"
    assert set(r["negativeCycle"]) == {"SCIENCE", "SOLA"}
    assert r["path"] == [] and r["dst"] is None and r["alternatives"] == []
    found = [e for e in r["events"] if e["type"] == "cycle_found"]
    assert len(found) == 1 and found[0]["cost"] == pytest.approx(-12.0)


def test_two_way_negative_road_is_a_negative_cycle():
    """A negative two-way road u-v is always a cycle u->v->u with negative total."""
    for edge in ("GOTA~SOLA", "PALDI~VSH"):
        roads = {edge: {"cost": -1}}
        city = dict(CITY, scenarios=CITY["scenarios"] + [{"id": "t", "roads": roads}])
        r = find_route(city, "GOTA", "ZYDUS", scenario="t")
        u, v = edge.split("~")
        assert r["negativeCycle"] is not None and set(r["negativeCycle"]) == {u, v}


def test_nearest_hospital_uses_bellman_ford_on_negative_map():
    r = find_route(CITY, "GOTA", "NEAREST", scenario="negative-road")
    assert r["algorithm"] == "bellman-ford" and r["dst"] in HOSPITALS


def test_engine_rejects_bad_input():
    with pytest.raises(ValueError):
        find_route(CITY, "NOPE", "ZYDUS")
    with pytest.raises(ValueError):
        find_route(CITY, "GOTA", "ZYDUS", scenario="nope")
    with pytest.raises(ValueError):
        find_route(CITY, "GOTA", "ZYDUS", algorithm="a-star")


@pytest.fixture
def client():
    from app import app
    app.testing = True
    return app.test_client()


def test_api_ok(client):
    r = client.post("/api/route", json={"src": "GOTA", "dst": "ZYDUS", "scenario": "negative-road"})
    assert r.status_code == 200 and round(r.get_json()["cost"], 2) == 17.67
    assert client.get("/api/scenarios").status_code == 200
    assert client.get("/api/route?src=GOTA&dst=ZYDUS").status_code == 200


@pytest.mark.parametrize("body", [
    {"src": "NOPE", "dst": "ZYDUS"},
    {"src": "GOTA", "dst": "NOPE"},
    {"src": "GOTA", "dst": "ZYDUS", "scenario": "nope"},
    {"src": "GOTA", "dst": "ZYDUS", "algorithm": "a-star"},
    {"src": "GOTA", "dst": "ZYDUS", "traffic": ["closed"]},
])
def test_api_returns_400_on_bad_input(client, body):
    r = client.post("/api/route", json=body)
    assert r.status_code == 400 and "error" in r.get_json()
