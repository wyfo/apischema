from __future__ import annotations

from typing import (Generic, Type, TypeVar)

MODEL_FIELD = "__model__"

Arg = TypeVar("Arg")


# TODO Full rework with PEP 593 (https://www.python.org/dev/peps/pep-0593/)
class Model(Generic[Arg]):
    def __class_getitem__(cls, params: Type):
        if cls is Model:
            class InstantiatedModel(cls, Generic[Arg]):  # type: ignore
                pass

            setattr(InstantiatedModel, MODEL_FIELD, params)
            return InstantiatedModel.__class_getitem__(params)
        else:
            return super().__class_getitem__(params)  # type: ignore

    @classmethod
    def from_model(cls, arg: Arg) -> Model[Arg]:
        # noinspection PyArgumentList
        return cls(arg)  # type: ignore

    def to_model(self) -> Arg:
        return getattr(self, MODEL_FIELD)(self)  # type: ignore


def get_model(cls: Type[Model]) -> Type:
    assert issubclass(cls, Model)
    return getattr(cls, MODEL_FIELD)
