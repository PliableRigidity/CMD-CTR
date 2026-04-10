from backend.app.models.world import WorldEvent


class WorldEventsService:
    def list_events(self) -> list[WorldEvent]:
        # Mock data removed per requirements. System should always rely on live RSS ingestion.
        return []
