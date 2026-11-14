"""Calendar (REST API): the meetings on the bar's own calendar."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import PolyConfigEntry, PolyCoordinator, PolyRestEntity
from .rest import PolyRestError


async def async_setup_entry(
    hass: HomeAssistant, entry: PolyConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    if coordinator.rest is not None:
        async_add_entities([PolyCalendar(coordinator)])


def _event(meeting: dict) -> CalendarEvent | None:
    start_ts = meeting.get("startTime")
    if not isinstance(start_ts, (int, float)) or meeting.get("canceled"):
        return None
    if start_ts > 1e11:  # milliseconds rather than seconds
        start_ts /= 1000
    start = datetime.fromtimestamp(start_ts, tz=timezone.utc)
    duration = meeting.get("duration")
    end = start + timedelta(seconds=duration if isinstance(duration, (int, float)) and duration > 0 else 1800)
    private = meeting.get("privateMeeting")
    return CalendarEvent(
        start=start,
        end=end,
        summary="Private meeting" if private else (meeting.get("subject") or "Meeting"),
        location=meeting.get("location") or None,
        description=None if private else (meeting.get("organizer") or None),
        uid=str(meeting["id"]) if meeting.get("id") else None,
    )


class PolyCalendar(PolyRestEntity, CalendarEntity):
    _attr_name = "Calendar"

    def __init__(self, coordinator: PolyCoordinator) -> None:
        super().__init__(coordinator, "calendar")

    @property
    def event(self) -> CalendarEvent | None:
        """Current meeting if there is one, otherwise the next upcoming one."""
        now = dt_util.utcnow()
        events = [e for m in self.rest_data.get("meetings") or [] if (e := _event(m)) and e.end > now]
        return min(events, key=lambda e: e.start) if events else None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        try:
            meetings = await self.coordinator.rest.meetings(
                int(start_date.timestamp()), int(end_date.timestamp())
            )
        except PolyRestError as err:
            raise HomeAssistantError(str(err)) from err
        events = [e for m in meetings if (e := _event(m))]
        return sorted(events, key=lambda e: e.start)
