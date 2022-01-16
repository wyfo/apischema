# flake8: noqa
from dataclasses import *


def _replace(__obj, **changes):
    from dataclasses import _FIELD_INITVAR, _FIELDS
    from dataclasses import replace as replace_

    from apischema.fields import FIELDS_SET_ATTR, fields_set, set_fields

    # Fix https://bugs.python.org/issue36470
    assert is_dataclass(__obj)
    for name, field in getattr(__obj, _FIELDS).items():
        if field._field_type == _FIELD_INITVAR and name not in changes:
            if field.default is not MISSING:
                changes[name] = field.default
            elif field.default_factory is not MISSING:
                changes[name] = field.default_factory()

    result = replace_(__obj, **changes)
    if hasattr(__obj, FIELDS_SET_ATTR):
        set_fields(result, *fields_set(__obj), *changes, overwrite=True)
    return result


globals()[replace.__name__] = _replace

del _replace
