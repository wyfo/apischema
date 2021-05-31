import collections.abc
import re
import sys
import warnings
from dataclasses import dataclass, field
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

from apischema.objects import AliasedStr
from apischema.typing import get_args, is_annotated
from apischema.utils import get_args2, get_origin2, merge_opts

try:
    from apischema.typing import Annotated
except ImportError:
    Annotated = ...  # type: ignore

ErrorMsg = str
Error = Union[ErrorMsg, Tuple[Any, ErrorMsg]]
# where  Any = Union[Field, int, str, Iterable[Union[Field, int, str,]]]
# but Field being kind of magic not understood by type checkers, it's hidden behind Any
ErrorKey = Union[AliasedStr, str, int]
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

    def __str__(self):
        return repr(self)

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


def _rec_build_error(path: Sequence[ErrorKey], msg: ErrorMsg) -> ValidationError:
    if not path:
        return ValidationError([msg])
    else:
        return ValidationError(children={path[0]: _rec_build_error(path[1:], msg)})


def _check_error_path(path) -> Sequence[ErrorKey]:
    if isinstance(path, (int, str)):
        path = (path,)
    for i, elt in enumerate(path):
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
        if not path:
            messages.append(msg)
        else:
            key, *remain = _check_error_path(path)
            children[key] = merge_errors(
                children.get(key), _rec_build_error(remain, msg)
            )
    return ValidationError(messages, children)


if sys.version_info >= (3, 7):  # pragma: no cover
    GeneratorOrigin = collections.abc.Generator
else:
    GeneratorOrigin = Generator  # pragma: no cover


# Looking forward to PEP 612
def gather_errors(func: Callable[..., ValidatorResult[T]]) -> Callable[..., T]:
    if not isgeneratorfunction(func):
        raise TypeError("func must be a generator returning a ValidatorResult")

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

    if "return" in func.__annotations__:
        ret = func.__annotations__["return"]
        if isinstance(ret, str):
            match = re.match(r"ValidatorResult\[(?P<ret>.*)\]", ret)
            if match is not None:
                ret = match.groupdict("ret")
        else:
            annotations = get_args(ret)[1:] if is_annotated(ret) else ()
            if get_origin2(ret) == GeneratorOrigin:
                ret = get_args2(ret)[2]
                if annotations:
                    ret = Annotated[(ret, *annotations)]
        wrapper.__annotations__["return"] = ret
    return wrapper


def with_validation_error(*args, **kwargs):
    warnings.warn(
        "with_validation_error is deprecated, use gather_errors instead",
        DeprecationWarning,
    )
    return gather_errors(*args, **kwargs)
