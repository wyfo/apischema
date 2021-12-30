from dataclasses import dataclass
from timeit import timeit
from typing import Annotated, Union

from apischema import deserialization_method, discriminator


@dataclass
class Cat:
    love_dog: bool = False


@dataclass
class Dog:
    love_cat: bool = False


Pet = Union[Cat, Dog]
DiscriminatedPet = Annotated[Pet, discriminator("type", {"dog": Dog})]

deserialize_union = deserialization_method(Union[Cat, Dog])
deserialize_discriminated = deserialization_method(
    Annotated[Union[Cat, Dog], discriminator("type")]
)
##### Without discrimininator
print(timeit('deserialize_union({"love_dog": False})', globals=globals()))
# Cat: 0.760085788
print(timeit('deserialize_union({"love_cat": False})', globals=globals()))
# Dog: 3.078876515 ≈ x4
##### With discriminator
print(timeit('deserialize_discriminated({"type": "Cat"})', globals=globals()))
# Cat: 1.244204702
print(timeit('deserialize_discriminated({"type": "Dog"})', globals=globals()))
# Dog: 1.234058598 ≈ same
