import json
from pathlib import Path
import pytest

VALID_APIFY_TYPES = {"string", "boolean", "integer", "object", "array"}
VALID_APIFY_EDITORS = {"textfield", "textarea", "javascript", "python", "select", "checkbox", "number", "json", "hidden"}

def test_apify_input_schema_strict_compliance():
    schema_path = Path(__file__).parent.parent / ".actor" / "input_schema.json"
    assert schema_path.exists(), f"Schema file not found at {schema_path}"

    with open(schema_path, "r", encoding="utf-8") as f:
        schema = json.load(f)

    # 1. Root Object Validation
    assert "title" in schema and isinstance(schema["title"], str) and len(schema["title"]) > 0
    assert "description" in schema and isinstance(schema["description"], str) and len(schema["description"]) > 0
    assert schema.get("type") == "object"
    assert schema.get("schemaVersion") == 1
    assert "properties" in schema and isinstance(schema["properties"], dict)

    # 2. Every Property Validation
    properties = schema["properties"]
    assert len(properties) >= 4, "Expected at least 4 properties"

    for prop_name, prop in properties.items():
        # Field 1: title
        assert "title" in prop, f"Property '{prop_name}' missing 'title'"
        assert isinstance(prop["title"], str) and len(prop["title"]) > 0, f"Property '{prop_name}' title invalid"

        # Field 2: type (MUST NOT BE 'number', only 'integer', 'string', etc.)
        assert "type" in prop, f"Property '{prop_name}' missing 'type'"
        assert prop["type"] in VALID_APIFY_TYPES, f"Property '{prop_name}' has invalid type '{prop['type']}'"

        # Field 3: description
        assert "description" in prop, f"Property '{prop_name}' missing 'description'"
        assert isinstance(prop["description"], str) and len(prop["description"]) > 0, f"Property '{prop_name}' description empty"

        # Field 4: editor
        assert "editor" in prop, f"Property '{prop_name}' missing 'editor'"
        assert prop["editor"] in VALID_APIFY_EDITORS, f"Property '{prop_name}' has invalid editor '{prop['editor']}'"

        # Enum & enumTitles check
        if "enum" in prop:
            assert prop["editor"] == "select", f"Property '{prop_name}' with enum must use editor 'select'"
            assert "enumTitles" in prop, f"Property '{prop_name}' with enum missing 'enumTitles'"
            assert isinstance(prop["enumTitles"], list), f"Property '{prop_name}' enumTitles must be list"
            assert len(prop["enum"]) == len(prop["enumTitles"]), (
                f"Property '{prop_name}' enum length ({len(prop['enum'])}) != enumTitles length ({len(prop['enumTitles'])})"
            )

def test_apify_actor_json_compliance():
    actor_path = Path(__file__).parent.parent / ".actor" / "actor.json"
    assert actor_path.exists(), f"actor.json file not found at {actor_path}"

    with open(actor_path, "r", encoding="utf-8") as f:
        actor = json.load(f)

    assert actor.get("actorSpecification") == 1
    assert actor.get("name") == "stealthguard-402"
    assert actor.get("version") == "1.0"
    assert actor.get("input") == "./input_schema.json"
    assert actor.get("output") == "./output_schema.json"
    assert actor.get("storages", {}).get("dataset") == "./dataset_schema.json"
    assert actor.get("dockerfile") == "../Dockerfile"
    assert "meta" not in actor, "Non-standard 'meta' key should not be present in actor.json"

def test_apify_output_schema_compliance():
    output_path = Path(__file__).parent.parent / ".actor" / "output_schema.json"
    assert output_path.exists(), f"output_schema.json not found at {output_path}"

    with open(output_path, "r", encoding="utf-8") as f:
        output_schema = json.load(f)

    assert output_schema.get("actorOutputSchemaVersion") == 1
    assert "title" in output_schema
    assert output_schema.get("type") == "object"
    assert "properties" in output_schema
    for prop_name, prop in output_schema["properties"].items():
        assert "template" in prop, f"Property '{prop_name}' missing required 'template'"
        assert isinstance(prop["template"], str) and len(prop["template"]) > 0

def test_apify_dataset_schema_compliance():
    dataset_path = Path(__file__).parent.parent / ".actor" / "dataset_schema.json"
    assert dataset_path.exists(), f"dataset_schema.json not found at {dataset_path}"

    with open(dataset_path, "r", encoding="utf-8") as f:
        dataset_schema = json.load(f)

    assert dataset_schema.get("actorSpecification") == 1
    assert "fields" in dataset_schema
    assert "views" in dataset_schema
    assert "overview" in dataset_schema["views"]

