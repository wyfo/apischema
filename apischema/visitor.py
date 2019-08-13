from typing import Callable, Generic, Optional, Type, TypeVar

import humps
from tmv import Visitor as BaseVisitor

from apischema.model import Model

Aliaser = Callable[[str], str]


def camel_case_aliaser(camel_case: bool) -> Aliaser:
    return humps.camelize if camel_case else None


Context = TypeVar("Context")
ReturnType = TypeVar("ReturnType")


# noinspection PyAbstractClass
class Visitor(BaseVisitor[ReturnType, Context], Generic[ReturnType, Context]):
    def __init__(self, aliaser: Optional[Aliaser]):
        super().__init__()
        self.aliaser = aliaser or (lambda s: s)

    def is_custom(self, cls: Type, ctx: Context) -> Optional[Type[Model]]:
        try:
            return cls if issubclass(cls, Model) else None
        except TypeError:
            return None
