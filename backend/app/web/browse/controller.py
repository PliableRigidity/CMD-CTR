from abc import ABC, abstractmethod

from backend.app.web.schemas.models import BrowserAction, BrowserSessionSnapshot


class BrowserAutomationProvider(ABC):
    @abstractmethod
    async def perform(self, action: BrowserAction) -> BrowserSessionSnapshot:
        raise NotImplementedError


class NullBrowserAutomationProvider(BrowserAutomationProvider):
    async def perform(self, action: BrowserAction) -> BrowserSessionSnapshot:
        return BrowserSessionSnapshot(
            status="not_implemented",
            current_url=action.target if action.action == "open" else None,
            extracted_text="Browser automation is scaffolded but not yet connected to a live driver.",
        )
