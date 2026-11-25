import sys
from dataclasses import dataclass
from typing import Union

import pytest

from apischema import deserialize


@pytest.mark.skipif(
    sys.version_info < (3, 12), reason="TypeAliasType requires Python 3.12"
)
def test_nested_type_alias_in_union():
    from typing import Literal, TypeAliasType

    @dataclass(kw_only=True)
    class XYZ:
        page: int
        location: Literal["XYZ"] = "XYZ"

    @dataclass(kw_only=True)
    class Fit:
        page: int
        location: Literal["Fit"] = "Fit"

    @dataclass(kw_only=True)
    class Reference:
        ref: str

    ExplicitDestination = TypeAliasType("ExplicitDestination", Union[XYZ, Fit])
    Destination = TypeAliasType("Destination", Union[Reference, ExplicitDestination])

    @dataclass(kw_only=True)
    class Model:
        title: str
        destination: Union[int, str, Destination]  # type: ignore[valid-type]

    assert deserialize(Model, {"title": "int", "destination": 42}).destination == 42
    assert (
        deserialize(Model, {"title": "str", "destination": "XLII"}).destination
        == "XLII"
    )
    assert deserialize(
        Model, {"title": "Reference", "destination": {"ref": "#foo"}}
    ).destination == Reference(ref="#foo")
    assert deserialize(
        Model, {"title": "Fit", "destination": {"location": "Fit", "page": 42}}
    ).destination == Fit(location="Fit", page=42)
    assert deserialize(
        Model, {"title": "XYZ", "destination": {"location": "XYZ", "page": 42}}
    ).destination == XYZ(location="XYZ", page=42)
