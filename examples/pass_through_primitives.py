from apischema import identity, serialization_method

assert serialization_method(list[int]) == identity
