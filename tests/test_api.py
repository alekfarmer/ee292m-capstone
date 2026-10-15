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
    assert "<title>Adder Gates</title>" in resp.text
