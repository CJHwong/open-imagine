"""The shared, persistent memory-policy setting in the public API."""


def settings_paths() -> dict:
    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["require_memory_estimate"],
        "properties": {"require_memory_estimate": {"type": "boolean", "default": True}},
    }
    response = {
        "description": "Settings shared by all workspaces and API callers. Known memory limits always apply.",
        "content": {"application/json": {"schema": schema}},
    }
    return {
        "/api/v1/settings": {
            "get": {
                "tags": ["studio"],
                "operationId": "readSettings",
                "summary": "Read app-wide settings",
                "responses": {"200": response},
            },
            "post": {
                "tags": ["studio"],
                "operationId": "updateSettings",
                "summary": "Persist app-wide settings for all callers",
                "description": "require_memory_estimate defaults to true. False permits unmeasured workflows; measured limits remain enforced. Private-key headers are refused. Stub settings last only for the server session.",
                "requestBody": {"required": True, "content": {"application/json": {"schema": schema}}},
                "responses": {
                    "200": response,
                    "400": {"description": "Invalid boolean, unknown setting, or private-key header"},
                },
            },
        }
    }
