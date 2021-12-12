from timeit import timeit

from apischema import deserialize

ints = list(range(100))

assert deserialize(list[int], ints, no_copy=True) is ints  # default
assert deserialize(list[int], ints, no_copy=False) is not ints

print(timeit("deserialize(list[int], ints, no_copy=True)", globals=globals()))
# 8.596703557006549
print(timeit("deserialize(list[int], ints, no_copy=False)", globals=globals()))
# 9.365363762015477
