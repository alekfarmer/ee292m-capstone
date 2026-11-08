"""The API serves the committed artifacts and validates its inputs."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import pipeline
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
    assert client.get("/api/programs").json() == ["sum", "tour"]
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


def test_a_typed_program_is_built_and_then_served_by_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(pipeline, "USER_DIR", tmp_path / "user")
    source = (
        "int main(void) {\n"
        "    int t = 0;\n"
        "    for (int i = 0; i < 4; i++)\n"
        "        t += 3;\n"
        "    return t;\n"
        "}\n"
    )
    resp = client.post("/api/programs", json={"source": source})
    assert resp.status_code == 200, resp.text
    name = resp.json()["program"]
    assert resp.json()["cached"] is False
    golden = client.get("/api/golden", params={"program": name}).json()
    assert golden["a0_at_halt"] == "0x0000000c"  # 3 + 3 + 3 + 3
    start = client.get("/api/start", params={"program": name}).json()["cycle"]
    view = client.get("/api/view/top.rv.dp", params={"cycle": start, "program": name})
    assert view.status_code == 200
    again = client.post("/api/programs", json={"source": source}).json()
    assert again == {"program": name, "cached": True}


def test_a_rejected_program_is_a_422_with_one_plain_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(pipeline, "USER_DIR", tmp_path / "user")
    resp = client.post("/api/programs", json={"source": "int main(void) { return 6 * 7; }\n"})
    assert resp.status_code == 422
    assert resp.json() == {
        "detail": "your_program.c:1: '*' is not supported: the core has no M extension "
        "(and pointers are outside the subset)"
    }


def test_the_request_body_is_validated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pipeline, "USER_DIR", tmp_path / "user")
    assert client.post("/api/programs", json={}).status_code == 422
    assert client.post("/api/programs", json={"source": ""}).status_code == 422
    assert client.post("/api/programs", json={"source": "x" * 2001}).status_code == 422
    extra = {"source": "int main(void) { return 0; }", "flags": "-O3"}
    assert client.post("/api/programs", json=extra).status_code == 422


def test_a_second_build_at_once_is_a_503(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pipeline, "USER_DIR", tmp_path / "user")
    with pipeline.BUILD_LOCK:
        resp = client.post("/api/programs", json={"source": "int main(void) { return 1; }\n"})
    assert resp.status_code == 503
    assert resp.headers["Retry-After"] == "2"
    assert "another program is being built" in resp.json()["detail"]
