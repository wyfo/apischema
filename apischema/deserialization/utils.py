from typing import Any, Dict, Iterable, List, Optional, Tuple, Union


def _rec_override(
    result: Optional[Union[Dict, List]], key: str, value: Any, separator: str
) -> Union[Dict, List]:
    assert key
    index: Any  # Use Any to prevent mypy to complain
    res: Any
    index, remains = key, None
    if separator in key:
        index, remains = key.split(separator, 1)
    if index.isdigit():
        if result is not None and not isinstance(result, list):
            raise ValueError(f"expected list at {key}")
        res = result or []
        index = int(index)
        if index >= len(res):
            res.extend([None] * (index - len(res) + 1))
    else:
        if result is not None and not isinstance(result, dict):
            raise ValueError(f"expected dict at {key}")
        res = result or {}
        res.setdefault(index, None)
    if remains:
        res[index] = _rec_override(res[index], remains, value, separator)
    else:
        res[index] = value
    return res


def unflat_key_value(items: Iterable[Tuple[str, Any]], *, separator: str = ".") -> Any:
    result = None
    for key, value in items:
        if not key:
            raise ValueError("empty keys are not handled")
        try:
            result = _rec_override(result, key, value, separator)
        except ValueError as err:
            raise ValueError(f"invalid key '{key}' ({err})")
    return result
