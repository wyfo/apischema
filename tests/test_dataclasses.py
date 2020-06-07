from dataclasses import InitVar, _FIELDS, dataclass, field

from apischema.dataclasses.cache import _resolve_init_var
from apischema.metadata.misc import init_var


@dataclass
class WithInitVar:
    a: InitVar[int] = field(metadata=init_var("int"))


def test_resolve_init_var():
    assert _resolve_init_var(WithInitVar, getattr(WithInitVar, _FIELDS)["a"]) == int
