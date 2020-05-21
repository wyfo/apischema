from dataclasses import Field, dataclass, field
from typing import (
    Any,
    Dict,
    Iterable,
    List,
    Mapping,
    Optional,
    Sequence,
    Tuple,
    Union,
    overload,
)

from apischema.alias import ALIAS_METADATA

ErrorMsg = str
Error = Union[ErrorMsg, Tuple[Any, ErrorMsg]]

ROOT_KEY = "."


@dataclass
class ValidationError(Exception):
    messages: Sequence[ErrorMsg] = field(default_factory=list)
    children: Mapping[str, "ValidationError"] = field(default_factory=dict)

    def flat(self) -> Iterable[Tuple[Tuple[str, ...], Sequence[ErrorMsg]]]:
        if self.messages:
            yield (), self.messages
        for child_path, child in self.children.items():
            for path, errors in child.flat():
                yield (child_path, *path), errors

    @property
    def flatten(self) -> Mapping[Tuple[str, ...], Sequence[ErrorMsg]]:
        return dict(self.flat())


@overload
def merge(err1: Optional[ValidationError], err2: ValidationError) -> ValidationError:
    ...


@overload
def merge(err1: ValidationError, err2: Optional[ValidationError]) -> ValidationError:
    ...


@overload
def merge(
    err1: Optional[ValidationError], err2: Optional[ValidationError]
) -> Optional[ValidationError]:
    ...


def merge(err1: Optional[ValidationError], err2: Optional[ValidationError]):
    if err1 is None:
        return err2
    if err2 is None:
        return err1
    return ValidationError(
        [*err1.messages, *err2.messages],
        {
            key: merge(err1.children.get(key), err2.children.get(key))  # type: ignore
            for key in err1.children.keys() | err2.children.keys()
        },
    )


def exception(err: Exception) -> str:
    return f"[{type(err).__name__}]{err}"


def _rec_build_error(path: Sequence[str], msg: ErrorMsg) -> ValidationError:
    if not path:
        return ValidationError([msg])
    else:
        return ValidationError(children={path[0]: _rec_build_error(path[1:], msg)})


def _check_error_path(path: Any) -> Sequence[str]:
    if isinstance(path, (Field, int, str)):
        path = [path]
    else:
        path = list(path)
    for i, elt in enumerate(path):
        if isinstance(elt, Field):
            path[i] = elt.metadata.get(ALIAS_METADATA, elt.name)
        elif isinstance(elt, int):
            path[i] = str(elt)
        if not isinstance(path[i], str):
            raise TypeError(
                f"Bad error path, expected Field, int or str," f" found {type(i)}"
            )
    return path


def build_from_errors(errors: Iterable[Error]) -> ValidationError:
    messages: List[ErrorMsg] = []
    children: Dict[str, ValidationError] = {}
    for error in errors:
        if isinstance(error, ErrorMsg):
            messages.append(error)
            continue
        path, msg = error
        path = _check_error_path(path)
        if not path:
            messages.append(msg)
        else:
            children[path[0]] = merge(
                children.get(path[0]), _rec_build_error(path[1:], msg)
            )
    return ValidationError(messages, children)
