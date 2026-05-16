from server.service.db.database import get_database, get_db_session, get_db
from server.service.application.user.utils import *
from fastapi import Request, WebSocket
from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from server.service.integrations import TranslationService, HandleMaskService, WebSocketManager
from server.service.application.tasks.manager import TaskAnalyzeManager

async def get_task_manager(
    request: Request = None,
    websocket: WebSocket = None
) -> TaskAnalyzeManager:
    """Универсальная зависимость для HTTP и WebSocket."""
    app = request.app if request else websocket.app
    return app.state.task_manager

async def get_websocket_manager(
    request: Request = None,
    websocket: WebSocket = None
) -> WebSocketManager:
    """Универсальная зависимость для HTTP и WebSocket."""
    app = request.app if request else websocket.app
    return app.state.ws_manager


def custom_openapi(app: FastAPI):
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title="DSA API",
        version="1.0.0",
        description="API",
        routes=app.routes,
    )

    path = "/api/image/{project_id}/images/upload"

    if path in openapi_schema["paths"]:
        post_schema = openapi_schema["paths"][path]["post"]

        content = (
            post_schema
            .get("requestBody", {})
            .get("content", {})
            .get("multipart/form-data", {})
        )

        schema_ref = content.get("schema", {}).get("$ref")

        if schema_ref:
            schema_name = schema_ref.split("/")[-1]

            schema = openapi_schema["components"]["schemas"][schema_name]

            properties = schema.get("properties", {})

            if "files" in properties:
                properties["files"] = {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "format": "binary"
                    },
                    "title": "Files"
                }

            if "mask_files" in properties:
                properties["mask_files"] = {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "format": "binary"
                    },
                    "title": "Mask Files"
                }

    app.openapi_schema = openapi_schema
    return app.openapi_schema

__all__ = [
    "custom_openapi",
    "get_database",
    "get_db",
    "get_db_session",
    "get_token", 
    "validate_token",
    "get_auth_data",
    "cheack_password",
    "is_too_similar",
    "search_check_user",
    "get_definition_user",
    "TranslationService",
    "HandleMaskService",
    "WebSocketManager",
    "get_websocket_manager",
    "TaskAnalyzeManager",
    "get_task_manager",
]