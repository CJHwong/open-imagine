"""Music clients get explicit request rules and readable response contracts."""

from studio.l3_interface_adapters.api.openapi import openapi_document


def test_music_requests_publish_conditional_requirements():
    schema = openapi_document()["components"]["schemas"]["MusicRequest"]
    assert len(schema["allOf"]) == 4
    assert schema["properties"]["reference_audio"]["pattern"]
    assert schema["properties"]["backend"]["minLength"] == 1
    assert schema["properties"]["seed"]["anyOf"][1] == {"const": ""}


def test_music_metadata_routes_publish_typed_results_and_errors():
    document = openapi_document()
    for path in ("/api/v1/operations/{id}/metadata", "/api/v1/operations/{id}/items/{index}/metadata"):
        route = document["paths"][path]["get"]
        assert {"200", "400", "404", "409"} <= route["responses"].keys()
        assert any(parameter["name"] == "X-Studio-Private-Key" for parameter in route["parameters"])
        schema = route["responses"]["200"]["content"]["application/json"]["schema"]
        assert schema == {"$ref": "#/components/schemas/MusicMetadataResult"}
    parameters = document["paths"]["/api/v1/operations/{id}/items/{index}/metadata"]["get"]["parameters"]
    assert parameters[1]["schema"] == {"type": "integer", "minimum": 1}
    result = document["components"]["schemas"]["MusicMetadataResult"]
    assert set(result["required"]) == {"score", "metadata", "seed", "seconds", "sample_rate", "stub"}
    assert result["properties"]["seconds"]["minimum"] == 0


def test_music_sync_headers_and_examples_are_discoverable():
    route = openapi_document()["paths"]["/api/v1/music/generate"]["post"]
    assert set(route["requestBody"]["content"]["application/json"]["examples"]) == {
        "generate",
        "instrumental",
        "plan",
        "render_score",
        "transcribe",
        "cover",
    }
    headers = route["responses"]["200"]["headers"]
    assert {
        "X-Studio-Operation",
        "X-Studio-Completed",
        "X-Studio-Seed",
        "X-Studio-Duration",
        "X-Studio-Sample-Rate",
        "X-Studio-Stub",
    } <= headers.keys()
    assert "WAV" in headers["X-Studio-Seed"]["description"]
    assert "startOperation" in route["description"]
    assert "createOperation" not in route["description"]
