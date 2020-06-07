from typing import NewType

from pytest import raises

from apischema import ValidationError, deserialize, serialize
from apischema.validation import add_validator

Palindrome = NewType("Palindrome", str)


@add_validator(Palindrome)
def check_palindrome(s: str):
    for i in range(len(s) // 2):
        if s[i] != s[-1 - i]:
            raise ValueError("Not a palindrome")


assert deserialize(Palindrome, "tacocat") == "tacocat"
with raises(ValidationError) as err:
    deserialize(Palindrome, "not a palindrome")
assert serialize(err.value) == [{"loc": [], "err": ["Not a palindrome"]}]
