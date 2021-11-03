from apischema import serialize

ints = list(range(5))
assert serialize(list[int], ints) is ints
