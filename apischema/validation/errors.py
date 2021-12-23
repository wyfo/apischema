from functools import reduce
from typing import (
    Any,
    Collection,
    Dict,
    Generator,
    Iterable,
    Iterator,
    List,
    Mapping,
    Optional,
    Sequence,
    Tuple,
    TypeVar,
    Union,
    overload,
)

from apischema.aliases import Aliaser
from apischema.objects import AliasedStr
from apischema.utils import merge_opts

try:
    from apischema.typing import Annotated
except ImportError:
    Annotated = ...  # type: ignore

ErrorMsg = str
Error = Union[ErrorMsg, Tuple[Any, ErrorMsg]]
# where  Any = Union[Field, int, str, Iterable[Union[Field, int, str,]]]
# but Field being kind of magic not understood by type checkers, it's hidden behind Any
ErrorKey = Union[str, int]
T = TypeVar("T")
ValidatorResult = Generator[Error, None, T]

try:
    from apischema.typing import TypedDict

    class LocalizedError(TypedDict):
        loc: Sequence[ErrorKey]
        err: ErrorMsg

except ImportError:
    LocalizedError = Mapping[str, Any]  # type: ignore


class ValidationError(Exception):
    @overload
    def __init__(self, __message: str):
        ...

    @overload
    def __init__(
        self,
        messages: Sequence[ErrorMsg] = None,
        children: Mapping[ErrorKey, "ValidationError"] = None,
    ):
        ...

    def __init__(
        self,
        messages: Union[ErrorMsg, Sequence[ErrorMsg]] = None,
        children: Mapping[ErrorKey, "ValidationError"] = None,
    ):
        if isinstance(messages, str):
            messages = [messages]
        self.messages: Sequence[str] = messages or []
        self.children: Mapping[ErrorKey, "ValidationError"] = children or {}

    def __str__(self):
        return f"{ValidationError.__name__}: {self.errors}"

    def _errors(self) -> Iterator[Tuple[List[ErrorKey], ErrorMsg]]:
        for msg in self.messages:
            yield [], msg
        for child_key in sorted(self.children):
            for path, error in self.children[child_key]._errors():
                yield [child_key, *path], error

    @property
    def errors(self) -> List[LocalizedError]:
        return [{"loc": path, "err": error} for path, error in self._errors()]

    @staticmethod
    def from_errors(errors: Sequence[LocalizedError]) -> "ValidationError":
        return reduce(
            merge_errors,
            [_rec_build_error(err["loc"], err["err"]) for err in errors],
            ValidationError(),
        )


@overload
def merge_errors(
    err1: Optional[ValidationError], err2: ValidationError
) -> ValidationError:
    ...


@overload
def merge_errors(
    err1: ValidationError, err2: Optional[ValidationError]
) -> ValidationError:
    ...


@overload
def merge_errors(
    err1: Optional[ValidationError], err2: Optional[ValidationError]
) -> Optional[ValidationError]:
    ...


@merge_opts  # type: ignore
def merge_errors(err1: ValidationError, err2: ValidationError) -> ValidationError:
    if err1 is None:
        return err2
    if err2 is None:
        return err1
    return ValidationError(
        [*err1.messages, *err2.messages],
        {
            key: merge_errors(  # type: ignore
                err1.children.get(key), err2.children.get(key)
            )
            for key in err1.children.keys() | err2.children.keys()
        },
    )


def apply_aliaser(error: ValidationError, aliaser: Aliaser) -> ValidationError:
    aliased, aliased_children = False, {}
    for key, child in error.children.items():
        if isinstance(key, AliasedStr):
            key = str(aliaser(key))  # str because it could be a str subclass
            aliased = True
        child2 = apply_aliaser(child, aliaser)
        aliased |= child2 is not child
        aliased_children[key] = child2
    return ValidationError(error.messages, aliased_children) if aliased else error


def _rec_build_error(path: Sequence[ErrorKey], msg: ErrorMsg) -> ValidationError:
    if not path:
        return ValidationError([msg])
    else:
        return ValidationError(children={path[0]: _rec_build_error(path[1:], msg)})


def build_validation_error(errors: Iterable[Error]) -> ValidationError:
    messages: List[ErrorMsg] = []
    children: Dict[ErrorKey, ValidationError] = {}
    for error in errors:
        if isinstance(error, ErrorMsg):
            messages.append(error)
            continue
        path, msg = error
        if not path:
            messages.append(msg)
        else:
            if isinstance(path, str) or not isinstance(path, Collection):
                path = (path,)
            key, *remain = path
            children[key] = merge_errors(
                children.get(key), _rec_build_error(remain, msg)
            )
    return ValidationError(messages, children)
