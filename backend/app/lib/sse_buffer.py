import time
from dataclasses import dataclass, field


@dataclass
class BufferedEvent:
    event_id: str
    event_kind: str
    property_id: str
    payload: str
    at: float = field(default_factory=time.time)


class SseReplayBuffer:
    """In-memory ring of recent SSE events for Last-Event-ID replay.

    One instance per worker process; shared across all client connections.
    """

    def __init__(self, window_seconds: int = 300):
        self._events: list[BufferedEvent] = []
        self._window = window_seconds

    def add(self, event: BufferedEvent) -> None:
        cutoff = time.time() - self._window
        self._events = [e for e in self._events if e.at >= cutoff]
        self._events.append(event)

    def events_since(self, last_event_id: str) -> list[BufferedEvent]:
        """Return all events after last_event_id, or [] if id not found."""
        for i, e in enumerate(self._events):
            if e.event_id == last_event_id:
                return self._events[i + 1:]
        return []
