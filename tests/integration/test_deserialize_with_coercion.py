from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping, Sequence, Union

from apischema import deserialize


def _coerce_json(cls, data):
    if not isinstance(data, cls) and isinstance(data, str):
        return json.loads(data)
    else:
        return data


@dataclass
class MyClass:
    my_property: Union[Sequence[str], Mapping[str, Any]]


def test_coerce_json():
    key = "test"
    value = 2
    ret = deserialize(
        MyClass,
        {
            "my_property": f'{{"{key}": {value}}}',
        },
        coerce=_coerce_json,
    )
    assert isinstance(ret, MyClass)
    assert isinstance(ret.my_property, dict) and ret.my_property[key] == value
