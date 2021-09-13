import json
from dataclasses import dataclass, field
from datetime import date

from apischema import order, serialize, serialized


@order({"trigram": order(-1)})
@dataclass
class User:
    firstname: str
    lastname: str
    address: str = field(metadata=order(after="birthdate"))
    birthdate: date = field()

    @serialized
    @property
    def trigram(self) -> str:
        return (self.firstname[0] + self.lastname[0] + self.lastname[-1]).lower()

    @serialized(order=order(before=birthdate))
    @property
    def age(self) -> int:
        age = date.today().year - self.birthdate.year
        if age > 0 and (date.today().month, date.today().day) < (
            self.birthdate.month,
            self.birthdate.day,
        ):
            age -= 1
        return age


user = User("Harry", "Potter", "London", date(1980, 7, 31))
dump = """{
    "trigram": "hpr",
    "firstname": "Harry",
    "lastname": "Potter",
    "age": 41,
    "birthdate": "1980-07-31",
    "address": "London"
}"""
assert json.dumps(serialize(User, user), indent=4) == dump
