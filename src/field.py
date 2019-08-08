from dataclasses import Field as BaseField, MISSING
from typing import Any, Optional


class Field(BaseField):
    # noinspection PyShadowingBuiltins
    def __init__(self, alias: Optional[str], default, default_factory,
                 init, repr, hash, compare, metadata, **kwargs):
        if alias is not None:
            self.alias = alias
        BaseField.__init__(self, default, default_factory,  # type: ignore
                           init, repr, hash, compare, metadata)
        assert "name" not in kwargs and "type" not in kwargs
        for attr, value in kwargs.items():
            setattr(self, attr, value)


# noinspection PyShadowingBuiltins
def field(alias: Optional[str] = None, *,
          default=MISSING, default_factory=MISSING,
          init=True, repr=True, hash=None,
          compare=True, metadata=None, **kwargs):
    return Field(alias=alias, default=default, default_factory=default_factory,
                 init=init, repr=repr, hash=hash, compare=compare,
                 metadata=metadata, **kwargs)


# noinspection PyShadowingNames
def has_default(field: BaseField) -> bool:
    return (field.default is not MISSING or
            field.default_factory is not MISSING)  # type: ignore


class NoDefault(Exception):
    pass


# noinspection PyShadowingNames
def get_default(field: BaseField) -> Any:
    if field.default is not MISSING:
        return field.default
    elif field.default_factory is not MISSING:  # type: ignore
        return field.default_factory()  # type: ignore
    raise NoDefault()


# noinspection PyShadowingNames
def get_aliased(field: BaseField):
    return getattr(field, "alias", field.name)
