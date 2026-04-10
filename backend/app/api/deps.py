from fastapi import Request

from backend.app.orchestration.assistant_router import AssistantPlatformRouter


def get_router(request: Request) -> AssistantPlatformRouter:
    return request.app.state.router
