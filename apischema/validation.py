from __future__ import annotations

from contextlib import contextmanager
from typing import (Any, Dict, Iterable, Iterator, List, Mapping, Tuple, Type,
                    TypeVar)

from apischema.errors import WRONG_TYPE
from apischema.validator import Error, ErrorMsg, Path, Validator

Cls = TypeVar("Cls")

Errors = List[Tuple[Path, ErrorMsg]]


class Validation:
    def __init__(self):
        self.errors: Errors = []

    # Could be optimized with a custom contextmanager
    @contextmanager
    def tmp_errors(self) -> Iterator[Errors]:
        save = self.errors
        self.errors = []
        yield self.errors
        self.errors = save

    def merge(self, *errors_list: Errors):
        for errors in errors_list:
            self.errors.extend(errors)

    def report(self, path: Path, error: Error) -> ValidationError:
        if isinstance(error, ErrorMsg):
            msg = error
        else:
            local_path, msg = error
            if isinstance(local_path, str):
                path = *path, local_path
            else:
                path = *path, *local_path
        self.errors.append((path, msg))
        return ValidationError(self)

    def report_many(self, path: Path, errors: Iterable[Error]) -> bool:
        # /!\ Use boolean var because errors can be a generator
        try:
            error_occurred = False
            for error in errors:
                self.report(path, error)
                error_occurred = True
            return error_occurred
        except Exception as err:
            self.report(path, str(err))
            return True

    def check_type(self, path: Path, data: Any, expected: Type):
        if not isinstance(data, expected):
            raise self.report(path, WRONG_TYPE.format(
                expected=expected.__name__, type=type(data).__name__
            ))

    def validate(self, path: Path, validators: Iterable[Validator],
                 to_validate: Any):
        error_occurred = False
        for validator in validators:
            error_occurred |= self.report_many(path, validator(to_validate))
        if error_occurred:
            raise ValidationError(self)

    def validate_one(self, path: Path, validator: Validator, to_validate: Any):
        if self.report_many(path, validator(to_validate)):
            raise ValidationError(self)


class ValidationError(Exception):
    # noinspection PyShadowingNames
    def __init__(self, validation: Validation):
        self.validation = validation

    @property
    def asdict(self) -> Mapping[Path, Iterable[str]]:
        res: Dict[Path, List[str]] = {}
        for path, msg in self.validation.errors:
            msgs = res.setdefault(path, [])
            msgs.append(msg)
        return res

    def __str__(self):
        return str(self.asdict)  # pragma: no cover
