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


@dataclass
class CompleteForm(PasswordForm):
    username: str


with raises(ValidationError) as err:
    deserialize(
        CompleteForm,
        {"username": "wyfo", "password": "p455w0rd", "confirmation": "..."},
    )
assert err.value.errors == [
    {"loc": [], "msg": "password doesn't match its confirmation"}
]
