from dataclasses import dataclass

import pytest

from apischema import ValidationError, deserialize, validator


@dataclass
class PasswordForm:
    password: str
    confirmation: str

    @validator
    def password_match(self):
        if self.password != self.confirmation:
            raise ValidationError("password doesn't match its confirmation")


@dataclass
class CompleteForm(PasswordForm):
    username: str


with pytest.raises(ValidationError) as err:
    deserialize(
        CompleteForm,
        {"username": "wyfo", "password": "p455w0rd", "confirmation": "..."},
    )
assert err.value.errors == [
    {"loc": [], "err": "password doesn't match its confirmation"}
]
