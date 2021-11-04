from datetime import datetime, timedelta

from apischema import deserialize

start = datetime.now()
end = datetime.now() + timedelta(1)
assert deserialize(
    tuple[datetime, datetime], [start, end], allowed_types={datetime}
) == (start, end)
