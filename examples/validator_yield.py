from dataclasses import dataclass
from ipaddress import IPv4Address, IPv4Network
from typing import List

from pytest import raises

from apischema import ValidationError, deserialize, serialize, validator
from apischema.fields import fields


@dataclass
class SubnetIps:
    subnet: IPv4Network
    ips: List[IPv4Address]

    @validator
    def check_ips_in_subnet(self):
        for index, ip in enumerate(self.ips):
            if ip not in self.subnet:
                # yield <error path>, <error message>
                yield (fields(self).ips, index), "ip not in subnet"


with raises(ValidationError) as err:
    deserialize(
        SubnetIps,
        {"subnet": "126.42.18.0/24", "ips": ["126.42.18.1", "126.42.19.0", "0.0.0.0"]},
    )
assert serialize(err.value) == [
    {"loc": ["ips", 1], "err": ["ip not in subnet"]},
    {"loc": ["ips", 2], "err": ["ip not in subnet"]},
]
