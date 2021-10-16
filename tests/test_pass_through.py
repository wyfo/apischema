from dataclasses import dataclass, field, make_dataclass
from functools import partial
from typing import Any, Dict, List, Optional, Union
from uuid import UUID

from pytest import mark

from apischema import UndefinedType, alias, properties, settings
from apischema.metadata import flatten, skip
from apischema.serialization import PassThroughOptions, pass_through
from apischema.utils import to_camel_case


@dataclass
class Flattened:
    field: int


@mark.parametrize(
    "option_and_field",
    [
        ("aliaser", ("with_underscore", int)),
        ("aliased_fields", ("aliased", int, field(metadata=alias("toto")))),
        ("flattened_fields", ("flattened", Flattened, field(metadata=flatten))),
        (
            "properties_fields",
            ("properties", Dict[str, int], field(metadata=properties)),
        ),
        ("skipped_fields", ("skipped", int, field(metadata=skip))),
        ("skipped_if_fields", ("skippedif", Union[int, UndefinedType])),
    ],
)
@mark.parametrize("has_field", [False, True])
@mark.parametrize("has_option", [False, True])
@mark.parametrize("uuid_field", [False, True])
def test_pass_through_dataclasses(option_and_field, has_field, has_option, uuid_field):
    fields: List[Any] = [("field", int)]
    if has_field:
        fields.append(option_and_field[1])
    if uuid_field:
        fields.append(("id", UUID))
    cls = make_dataclass("Data", fields)
    rec_cls = make_dataclass("RecData", [("rec", ...)], bases=(cls,))
    rec_cls.__annotations__["rec"] = Optional[rec_cls]
    options = PassThroughOptions(
        dataclasses=PassThroughOptions.Dataclass(**{option_and_field[0]: has_option})
    )
    pass_through_result = not uuid_field and (has_option or not has_field)
    pass_through2 = partial(
        pass_through,
        additional_properties=False,
        aliaser=to_camel_case,
        conversion=None,
        default_conversion=settings.serialization.default_conversion,
        exclude_defaults=False,
        exclude_none=False,
        exclude_unset=False,
        options=options,
    )
    assert pass_through2(cls) == pass_through2(rec_cls) == pass_through_result
