from typing import NewType

from pytest import raises

from apischema import ValidationError, deserialize, serialize, validator

Palindrome = NewType("Palindrome", str)


@validator
def check_palindrome(s: Palindrome):
    for i in range(len(s) // 2):
        if s[i] != s[-1 - i]:
            raise ValueError("Not a palindrome")


assert deserialize(Palindrome, "tacocat") == "tacocat"
with raises(ValidationError) as err:
    deserialize(Palindrome, "this is not a palindrome")
assert serialize(err.value) == [{"loc": [], "err": ["Not a palindrome"]}]
