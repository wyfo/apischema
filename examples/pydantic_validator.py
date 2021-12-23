from dataclasses import dataclass

import pydantic

import apischema


class UserModel(pydantic.BaseModel):
    username: str
    password1: str
    password2: str

    @pydantic.root_validator
    def check_passwords_match(cls, values):
        # This is a classmethod (it needs a plugin to not raise a warning in your IDE)
        # What is the type of of values? of values['password1']?
        # If you rename password1 field, validator will hardly be updated
        # You also have to test yourself that values are provided
        pw1, pw2 = values.get("password1"), values.get("password2")
        if pw1 is not None and pw2 is not None and pw1 != pw2:
            raise ValueError("passwords do not match")
        return values


@dataclass
class LoginForm:
    username: str
    password1: str
    password2: str

    @apischema.validator
    def check_password_match(self):
        # Typed checked, simpler, and not executed if password1 or password2
        # are missing/invalid
        if self.password1 != self.password2:
            raise ValueError("passwords do not match")
