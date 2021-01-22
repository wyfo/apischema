import collections.abc
import re
import sys
from dataclasses import Field, dataclass, field
from functools import reduce, wraps
from inspect import isgeneratorfunction
from typing import (
    Any,
    Callable,
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
    cast,
    overload,
)

from apischema.aliases import Aliaser
from apischema.dataclass_utils import get_alias
from apischema.dataclasses import replace
from apischema.typing import get_args, get_origin
from apischema.utils import get_args2, get_origin2, merge_opts

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


@dataclass
class LocalizedError:
    loc: Sequence[ErrorKey]
    err: Sequence[ErrorMsg]

    def nested(self, index=0) -> "ValidationError":
        if index == len(self.loc):
            return ValidationError(self.err)
        else:
            assert index < len(self.loc)
            return ValidationError(children={self.loc[index]: self.nested(index + 1)})


@dataclass
class ValidationError(Exception):
    messages: Sequence[ErrorMsg] = field(default_factory=list)
    children: Mapping[ErrorKey, "ValidationError"] = field(default_factory=dict)

    def flat(self) -> Iterator[Tuple[Tuple[ErrorKey, ...], Sequence[ErrorMsg]]]:
        if self.messages:
            yield (), self.messages
        for child_key in sorted(self.children):
            for path, errors in self.children[child_key].flat():
                yield (child_key, *path), errors

    def serialize(self) -> Sequence[LocalizedError]:
        return [LocalizedError(loc, err) for loc, err in self.flat()]

    @staticmethod
    def deserialize(errors: Sequence[LocalizedError]) -> "ValidationError":
        return reduce(
            merge_errors, map(LocalizedError.nested, errors), ValidationError()
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


def exception(err: Exception) -> str:
    return str(err)


def _rec_build_error(path: Sequence[str], msg: ErrorMsg) -> ValidationError:
    if not path:
        return ValidationError([msg])
    else:
        return ValidationError(children={path[0]: _rec_build_error(path[1:], msg)})


class FieldPath(str):
    def __new__(cls, field: Field):
        obj = super().__new__(cls, field.name)  # type: ignore
        obj.field = field  # type: ignore
        return obj


def _check_error_path(path) -> Sequence[ErrorKey]:
    if isinstance(path, (Field, int, str)):
        path = [path]
    else:
        path = list(path)
    for i, elt in enumerate(path):
        if isinstance(elt, Field):
            path[i] = FieldPath(elt)
        if not isinstance(path[i], (str, int)):
            raise TypeError(
                f"Bad error path, expected Field, int or str," f" found {type(i)}"
            )
    return cast(Sequence[ErrorKey], path)


def build_validation_error(errors: Iterable[Error]) -> ValidationError:
    messages: List[ErrorMsg] = []
    children: Dict[ErrorKey, ValidationError] = {}
    for error in errors:
        if isinstance(error, ErrorMsg):
            messages.append(error)
            continue
        path, msg = error
        path = _check_error_path(path)
        if not path:
            messages.append(msg)
        else:
            key, *remain = path
            children[key] = merge_errors(
                children.get(key), _rec_build_error(remain, msg)
            )
    return ValidationError(messages, children)


def apply_aliaser(error: ValidationError, aliaser: Aliaser) -> ValidationError:
    path_replace: Dict[ErrorKey, str] = {}
    error_replace = {}
    for path, child_error in error.children.items():
        if isinstance(path, FieldPath):
            path_replace[path] = aliaser(get_alias(path.field))  # type: ignore
        new_error = apply_aliaser(child_error, aliaser)
        if new_error is not child_error:
            error_replace[path] = new_error
    if path_replace or error_replace:
        return replace(
            error,
            children={
                path_replace.get(path, path): error_replace.get(path, err)
                for path, err in error.children.items()
            },
        )
    else:
        return error


if sys.version_info >= (3, 7):  # pragma: no cover
    GeneratorOrigin = collections.abc.Generator
else:
    GeneratorOrigin = Generator  # pragma: no cover


def yield_to_raise(func: Callable[..., ValidatorResult[T]]) -> Callable[..., T]:
    @wraps(func)
    def wrapper(*args, **kwargs):
        result, errors = func(*args, **kwargs), []
        while True:
            try:
                errors.append(next(result))
            except StopIteration as stop:
                if errors:
                    raise build_validation_error(errors)
                return stop.value

    return wrapper


# Looking forward to PEP 612
def with_validation_error(func: Callable[..., ValidatorResult[T]]) -> Callable[..., T]:
    if not isgeneratorfunction(func):
        raise TypeError("func must be a generator returning a ValidatorResult")
    wrapper = yield_to_raise(func)
    if "return" in func.__annotations__:
        ret = func.__annotations__["return"]
        if isinstance(ret, str):
            match = re.match(r"ValidatorResult\[(?P<ret>.*)\]", ret)
            if match is not None:
                ret = match.groupdict("ret")
        else:
            annotations = get_args(ret)[1:] if get_origin(ret) == Annotated else ()
            if get_origin2(ret) == GeneratorOrigin:
                ret = get_args2(ret)[2]
                if annotations:
                    ret = Annotated[(ret, *annotations)]
        wrapper.__annotations__["return"] = ret
    return wrapper
