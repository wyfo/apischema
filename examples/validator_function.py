from typing import Annotated, NewType

from pytest import raises

from apischema import ValidationError, deserialize, serialize, validator
from apischema.metadata import validators

Palindrome = NewType("Palindrome", str)


@validator
def check_palindrome(s: Palindrome):
    for i in range(len(s) // 2):
        if s[i] != s[-1 - i]:
            raise ValueError("Not a palindrome")


assert deserialize(Palindrome, "tacocat") == "tacocat"
with raises(ValidationError) as err:
    deserialize(Palindrome, "palindrome")
assert serialize(err.value) == [{"loc": [], "err": ["Not a palindrome"]}]

# Using Annotated
with raises(ValidationError) as err:
    deserialize(Annotated[str, validators(check_palindrome)], "palindrom")
assert serialize(err.value) == [{"loc": [], "err": ["Not a palindrome"]}]
