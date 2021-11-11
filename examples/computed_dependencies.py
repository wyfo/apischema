from dataclasses import dataclass

from pytest import raises

from apischema import ValidationError, deserialize, validator


@dataclass
class PasswordForm:
    password: str
    confirmation: str

    @validator
    def password_match(self):
        if self.password != self.confirmation:
            raise ValueError("password doesn't match its confirmation")


with raises(ValidationError) as err:
    deserialize(PasswordForm, {"password": "p455w0rd"})
assert err.value.errors == [
    # validator is not executed because confirmation is missing
    {"loc": ["confirmation"], "err": "missing property"}
]
