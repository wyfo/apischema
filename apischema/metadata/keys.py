from apischema.utils import PREFIX


def metadata_key(key: str) -> str:
    return PREFIX + key


ALIAS_METADATA = metadata_key("alias")
ALIAS_NO_OVERRIDE_METADATA = metadata_key("alias_no_override")
CONVERSION_METADATA = metadata_key("conversion")
DEFAULT_AS_SET_METADATA = metadata_key("default_as_set")
DISCRIMINATOR_METADATA = metadata_key("discriminator")
FALL_BACK_ON_DEFAULT_METADATA = metadata_key("fall_back_on_default")
FLATTEN_METADATA = metadata_key("flattened")
INIT_VAR_METADATA = metadata_key("init_var")
NONE_AS_UNDEFINED_METADATA = metadata_key("none_as_undefined")
ORDERING_METADATA = metadata_key("ordering")
POST_INIT_METADATA = metadata_key("post_init")
PROPERTIES_METADATA = metadata_key("properties")
REQUIRED_METADATA = metadata_key("required")
SCHEMA_METADATA = metadata_key("schema")
SKIP_METADATA = metadata_key("skip")
VALIDATORS_METADATA = metadata_key("validators")
