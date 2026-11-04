"""The API serves the committed artifacts and validates its inputs."""

from fastapi.testclient import TestClient

from app.api import app
from tests.svg_reading import read_sum

client = TestClient(app)


def test_health() -> None:
    assert client.get("/api/health").json() == {"status": "ok"}


def test_adder_case_is_served_with_correct_values() -> None:
    body = client.get("/api/adder/5_plus_3").json()
    assert (body["sum"], body["cout"]) == ("0x00000008", 0)
    assert read_sum(body["svg"]) == (8, 0)


def test_adder_cases_listed() -> None:
    ids = [c["case_id"] for c in client.get("/api/adder").json()]
    assert ids == ["5_plus_3", "ffffffff_plus_1"]


def test_unknown_case_is_404_with_a_message() -> None:
    resp = client.get("/api/adder/nope")
    assert resp.status_code == 404
    assert "nope" in resp.json()["detail"]


def test_malformed_case_id_is_rejected() -> None:
    assert client.get("/api/adder/BAD-ID!").status_code == 422


def test_gate_counts_and_program_served() -> None:
    counts = client.get("/api/gate-counts").json()
    assert {r["module"] for r in counts["summary"]} >= {"top", "alu", "maindec", "controller"}
    program = client.get("/api/program").json()
    assert program["source_file"] == "sum.c"
    golden = client.get("/api/golden").json()
    assert golden["a0_at_halt"] == "0x00000037"


def test_page_is_served() -> None:
    resp = client.get("/")
    assert resp.status_code == 200
    assert "<title>C to Gates</title>" in resp.text


def test_page_files_are_revalidated_so_an_update_is_never_stale() -> None:
    """A browser may keep a file but must ask again before using it (a 304 if unchanged)."""
    for path in ("/", "/app.js", "/graph.js", "/styles.css"):
        resp = client.get(path)
        assert resp.status_code == 200, path
        assert resp.headers.get("cache-control") == "no-cache", path
    etag = client.get("/graph.js").headers["etag"]
    assert client.get("/graph.js", headers={"if-none-match": etag}).status_code == 304


def test_cycle_and_view_endpoints() -> None:
    cv = client.get("/api/cycle/0").json()
    assert cv["pc"] == "0x80000000" and cv["cycle"] == 0
    view = client.get("/api/view/top.rv.dp", params={"cycle": 0}).json()
    assert view["module"] == "datapath" and view["kind"] == "blocks"
    pc = next(e for e in view["edges"] if e["target"] == "out:pc")
    assert pc["value"] == "0x80000000"
    assert [s["id"] for s in view["stages"]] == ["IF", "ID", "EX", "MEM", "WB"]
    assert {n["id"]: n["stage"] for n in view["nodes"]}["alu"] == "EX"


def test_view_inputs_are_validated() -> None:
    assert client.get("/api/view/top.nope").status_code == 404
    assert client.get("/api/view/../etc").status_code in (404, 422)
    assert client.get("/api/view/top.rv.dp", params={"cycle": -1}).status_code == 422
    assert client.get("/api/view/top.rv.dp", params={"cycle": 9999}).status_code == 404
    assert client.get("/api/cycle/9999").status_code == 404


def test_programs_are_listed_and_chosen_by_name() -> None:
    assert client.get("/api/programs").json() == ["sum"]
    assert client.get("/api/golden", params={"program": "sum"}).json()["exit_code"] == 55
    assert client.get("/api/golden", params={"program": "nope"}).status_code == 404
    assert client.get("/api/golden", params={"program": "../x"}).status_code == 422
    view = client.get("/api/view/top.rv.dp", params={"cycle": 0, "program": "sum"})
    assert view.status_code == 200
    assert client.get("/api/cycle/0", params={"program": "nope"}).status_code == 404


def test_start_cycle_served_and_unknown_program_is_404() -> None:
    body = client.get("/api/start").json()
    assert body["cycle"] == 11
    assert body["reason"] == "the first time the program loops back"
    assert client.get("/api/start?program=nope").status_code == 404
