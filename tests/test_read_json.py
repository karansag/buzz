"""The faster read response keeps the previous FastAPI JSON contract."""

from datetime import datetime, timezone
import json

import pytest
from fastapi.encoders import jsonable_encoder
from starlette.responses import JSONResponse

from agent_swarm.server import _read_json


@pytest.mark.parametrize("value", [
    {"rows": [{"id": 2**63 - 1, "ts": 1789572051.1234567, "text": "café 🐝\n"}],
     "floats": [-0.0, 1e-7, 1e20], "more": False, "next": None},
    {"numeric_keys": {42: "value"}},
    {"large_int": 2**100},
    {"legacy": [datetime(2026, 11, 22, 12, tzinfo=timezone.utc), {"alpha", "beta"}]},
])
def test_read_json_matches_fastapi(value):
    expected = JSONResponse(jsonable_encoder(value))
    actual = _read_json(value)
    assert actual.status_code == expected.status_code
    assert actual.headers["content-type"] == expected.headers["content-type"]
    assert json.dumps(json.loads(actual.body), sort_keys=True) == json.dumps(
        json.loads(expected.body), sort_keys=True
    )


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_read_json_keeps_rejecting_nonfinite_numbers(value):
    with pytest.raises(ValueError, match="Out of range float"):
        _read_json({"rows": [{"ts": value}]})
