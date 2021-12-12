from typing import Dict, List, Optional

import pytest

from apischema import deserialize, serialize


@pytest.mark.parametrize(
    "data, tp",
    [([0], List[int]), ({"": 0}, Dict[str, int]), ([None, 0], List[Optional[int]])],
)
def test_no_copy(data, tp):
    assert deserialize(tp, data, no_copy=True) is data
    obj = deserialize(tp, data, no_copy=False)
    assert obj == data and obj is not data
    assert serialize(tp, obj, no_copy=True) is obj
    data = serialize(tp, obj, no_copy=False)
    assert data == obj and data is not obj
