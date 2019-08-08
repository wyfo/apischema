import humps  # type: ignore


def camelize(s: str, when: bool = True) -> str:
    return humps.camelize(s) if when else s
