from datetime import datetime

from apischema import deserialize

now = datetime.now()
assert deserialize(list[datetime], [now], pass_through={datetime}) == [now]
