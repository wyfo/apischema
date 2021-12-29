import marshmallow.validate
from common import Benchmark, Methods, Payment, to_camel_case


# https://marshmallow.readthedocs.io/en/latest/examples.html#inflection-camel-casing-keys
class CamelCaseSchema(marshmallow.Schema):
    """Schema that uses camel-case for its external representation
    and snake-case for its internal representation.
    """

    def on_bind_field(self, field_name, field_obj):
        field_obj.data_key = to_camel_case(field_obj.data_key or field_name)


class Message(CamelCaseSchema):
    title = marshmallow.fields.Str(required=True)
    body = marshmallow.fields.Str(required=True)
    addresses = marshmallow.fields.List(marshmallow.fields.Str)
    persistence = marshmallow.fields.Int()


class Client(CamelCaseSchema):
    id = marshmallow.fields.Int(
        required=True, validate=marshmallow.validate.Range(min=0)
    )
    first_name = marshmallow.fields.Str(required=True)
    last_name = marshmallow.fields.Str(required=True)


class Item(CamelCaseSchema):
    name = marshmallow.fields.Str(required=True)
    price = marshmallow.fields.Float(
        required=True, validate=marshmallow.validate.Range(min=0)
    )
    quantity = marshmallow.fields.Int(
        default=1, validate=marshmallow.validate.Range(min=1)
    )


class Receipt(CamelCaseSchema):
    store = marshmallow.fields.Str(required=True)
    address = marshmallow.fields.Str(required=True)
    date = marshmallow.fields.DateTime(required=True)
    items = marshmallow.fields.List(marshmallow.fields.Nested(Item), required=True)
    payment = marshmallow.fields.Str(
        required=True, validate=marshmallow.validate.OneOf({e.value for e in Payment})
    )
    client = marshmallow.fields.Nested(Client)
    special_offers = marshmallow.fields.Float(
        validate=marshmallow.validate.Range(min=0)
    )

    @marshmallow.post_load
    def convert_payment_to_enum(self, data, **kwargs):
        data["payment"] = Payment(data["payment"])
        return data


def methods(cls: type[CamelCaseSchema]) -> Methods:
    return Methods(cls(many=True).load, cls(many=True).dump)


benchmarks = Benchmark(methods(Message), methods(Receipt))
