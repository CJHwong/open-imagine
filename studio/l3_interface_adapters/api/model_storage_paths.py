"""Public inventory, preview and explicit removal of declared model assets."""


def model_storage_paths():
    selection = {
        "type": "object",
        "additionalProperties": False,
        "required": ["models"],
        "properties": {
            "models": {"type": "array", "minItems": 1, "uniqueItems": True, "items": {"type": "string"}},
            "include_runtime": {"type": "boolean", "default": False},
        },
    }
    responses = {
        "200": {"description": "JSON inventory, cleanup preview, or removed asset IDs and reclaimed bytes."},
        "400": {"description": "Invalid selection, changed files, or private-key header."},
        "409": {"description": "Another operation owns model memory."},
    }
    paths = {
        "/api/v1/model-storage": {
            "get": {
                "tags": ["studio"],
                "operationId": "inspectModelStorage",
                "summary": "List declared downloaded assets, including hidden optional models",
                "responses": {"200": responses["200"]},
                "description": "Read-only. Stub servers return available=false and never inspect real caches. Private-key headers are refused.",
            }
        }
    }
    for action, summary in (
        ("plan", "Preview cleanup without deleting files"),
        ("remove", "Remove a reviewed selection while Studio is idle"),
    ):
        schema = (
            selection
            if action == "plan"
            else {
                **selection,
                "required": ["models", "revision"],
                "properties": {**selection["properties"], "revision": {"type": "string"}},
            }
        )
        paths["/api/v1/model-storage/" + action] = {
            "post": {
                "tags": ["studio"],
                "operationId": "modelStorage" + action.title(),
                "summary": summary,
                "description": "Send model IDs, never filesystem paths. Shared assets require every owning model selected. Runtime removal is opt-in. External, symlinked, overlapping and installed-plugin checkpoint assets are protected. Removal requires the inventory revision returned by plan; changed files invalidate it. This deletes downloads, not generated media or configured user LoRAs. Missing weights may download again on the next run. Private-key headers are refused.",
                "requestBody": {"required": True, "content": {"application/json": {"schema": schema}}},
                "responses": responses,
            }
        }
    return paths
