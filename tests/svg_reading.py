"""Read values back out of the rendered adder SVG, as a viewer would see them."""

import xml.etree.ElementTree as ET


def wire_values(svg: str, net: str) -> dict[int, int]:
    """Map bit -> value for every wire element of ``net``.

    Raises AssertionError if two segments of the same net in one bit disagree.
    """
    values: dict[int, int] = {}
    for el in ET.fromstring(svg).iter():
        if el.get("data-net") != net or "wire" not in (el.get("class") or ""):
            continue
        bit, value = int(el.get("data-bit", "-1")), int(el.get("data-value", "-1"))
        assert value in (0, 1), f"wire {net}[{bit}] has value {value}"
        assert f"v{value}" in (el.get("class") or "").split(), "class does not match value"
        assert values.setdefault(bit, value) == value, f"segments of {net}[{bit}] disagree"
    return values


def read_sum(svg: str) -> tuple[int, int]:
    """Return (sum, carry out) as drawn: the s wires of bits 0..31 and cout of bit 31."""
    s = wire_values(svg, "s")
    assert sorted(s) == list(range(32)), "the drawing must show one sum wire per bit"
    cout = wire_values(svg, "cout")
    return sum(v << i for i, v in s.items()), cout[31]
