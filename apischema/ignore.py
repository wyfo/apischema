from apischema.types import DictWithUnion, Metadata
from apischema.utils import PREFIX


class Ignored(Exception):
    pass


IGNORE_METADATA = f"{PREFIX}ignore"


def ignore_default() -> Metadata:
    return DictWithUnion({IGNORE_METADATA: True})
