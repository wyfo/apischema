from datetime import datetime

from apischema import deserialize

now = datetime.now()
assert deserialize(list[datetime], [now], allowed_types={datetime}) == [now]
