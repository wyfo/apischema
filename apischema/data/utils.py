from typing import Any, Dict, Iterable, List, Optional, Tuple, Union


def override_data(
    obj: Optional[Union[Dict, List]], key: str, value: Any, separator: str
) -> Union[Dict, List]:
    assert key
    # Use Any to prevent mypy to complain
    index: Any
    res: Any
    index, remains = key, None
    if separator in key:
        index, remains = key.split(separator, 1)
    if index.isdigit():
        if obj is not None and not isinstance(obj, list):
            raise ValueError(f"expected list at {key}")
        res = obj or []
        index = int(index)
        if index >= len(res):
            res.extend([None] * (index - len(res) + 1))
    else:
        if obj is not None and not isinstance(obj, dict):
            raise ValueError(f"expected dict at {key}")
        res = obj or {}
        res.setdefault(index, None)
    if remains:
        res[index] = override_data(res[index], remains, value, separator)
    else:
        res[index] = value
    return res


def items_to_data(items: Iterable[Tuple[str, Any]], *, separator: str = ".") -> Any:
    data = None
    for key, value in items:
        if not key:
            raise ValueError("empty keys are not handled")
        try:
            data = override_data(data, key, value, separator)
        except ValueError as err:
            raise ValueError(f"invalid key '{key}' ({err})")
    return data
