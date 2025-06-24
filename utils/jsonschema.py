import jsonschema

def validate_json_schema(instance, schema):
    # If schema is None, skip validation
    if schema is None:
        return
    
    try:
        jsonschema.validate(instance=instance, schema=schema)
    except jsonschema.ValidationError as e:
        raise ValueError(f"JSON Schema validation error: {e.message}") 