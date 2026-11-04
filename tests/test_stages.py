"""The datapath view is labelled with the five textbook stages.

Each datapath block and port belongs to exactly one stage, placed as in the
Patterson & Hennessy and Harris & Harris single-cycle figures; other views
carry no stages.
"""

from pathlib import Path

from app import pipeline

ORDER = ["IF", "ID", "EX", "MEM", "WB"]

# Read off the textbook figures (and backend/rtl/datapath.sv), not views code.
EXPECTED = {
    "pcreg": "IF",
    "pcadd4": "IF",
    "pcmux": "IF",
    "in:instr": "IF",
    "out:pc": "IF",
    "rf": "ID",
    "ext": "ID",
    "srcamux": "EX",
    "srcbmux": "EX",
    "alu": "EX",
    "pcaddbranch": "EX",
    "lsu": "MEM",
    "in:readword": "MEM",
    "out:writedata": "MEM",
    "out:byteen": "MEM",
    "resultmux": "WB",
}


def test_the_datapath_has_the_five_stages_in_order(fresh_dir: Path) -> None:
    view = pipeline.get_module_view("top.rv.dp", 11, fresh_dir)
    assert view.stages is not None
    assert [s.id for s in view.stages] == ORDER
    assert [s.name for s in view.stages] == ["fetch", "decode", "execute", "memory", "write-back"]
    assert all(s.note for s in view.stages)


def test_every_datapath_node_has_one_stage(fresh_dir: Path) -> None:
    view = pipeline.get_module_view("top.rv.dp", 11, fresh_dir)
    missing = [n.id for n in view.nodes if n.stage not in ORDER]
    assert missing == [], f"datapath nodes without a stage: {missing}"
    stage = {n.id: n.stage for n in view.nodes}
    for node_id, want in EXPECTED.items():
        assert stage[node_id] == want, node_id


def test_a_constant_sits_in_the_stage_of_the_block_it_feeds(fresh_dir: Path) -> None:
    view = pipeline.get_module_view("top.rv.dp", 11, fresh_dir)
    stage = {n.id: n.stage for n in view.nodes}
    consts = [e for e in view.edges if e.source.startswith("const:")]
    assert consts  # pcadd4's 4, for one
    for e in consts:
        assert stage[e.source] == stage[e.target], e.id


def test_other_views_have_no_stages(fresh_dir: Path) -> None:
    for path in ("top", "top.rv", "top.rv.dp.alu", "top.rv.c.md"):
        view = pipeline.get_module_view(path, 11, fresh_dir)
        assert view.stages is None, path
        assert all(n.stage is None for n in view.nodes), path
