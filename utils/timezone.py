from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


UTC = timezone.utc
DEFAULT_TIMEZONE_NAME = "UTC"


def timezone_from_name(value: str | None) -> ZoneInfo:
    name = str(value or DEFAULT_TIMEZONE_NAME).strip() or DEFAULT_TIMEZONE_NAME

    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo(DEFAULT_TIMEZONE_NAME)


def user_timezone_name() -> str:
    """Return the IANA timezone reported by the active browser session."""
    try:
        import streamlit as st
        from streamlit.runtime.scriptrunner import get_script_run_ctx

        if get_script_run_ctx(suppress_warning=True) is None:
            return DEFAULT_TIMEZONE_NAME

        name = str(st.context.timezone or "").strip()
    except (AttributeError, RuntimeError, TypeError):
        name = ""

    if not name:
        return DEFAULT_TIMEZONE_NAME

    zone = timezone_from_name(name)
    return zone.key


def user_timezone() -> ZoneInfo:
    return timezone_from_name(user_timezone_name())


def utc_now() -> datetime:
    return datetime.now(UTC)


def user_now() -> datetime:
    return utc_now().astimezone(user_timezone())


def user_today() -> date:
    return user_now().date()


def parse_utc_datetime(value) -> datetime:
    """Parse database timestamps, treating legacy naive values as UTC."""
    if isinstance(value, datetime):
        parsed = value
    else:
        normalized = str(value or "").strip()

        if not normalized:
            raise ValueError("A date and time value is required.")

        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)

    return parsed.astimezone(UTC)


def to_user_datetime(value) -> datetime:
    return parse_utc_datetime(value).astimezone(user_timezone())


def to_named_timezone(value, timezone_name: str) -> datetime:
    return parse_utc_datetime(value).astimezone(timezone_from_name(timezone_name))


def local_datetime_to_utc(
    value: datetime,
    timezone_name: str | None = None,
) -> datetime:
    """Interpret a browser-entered wall time and convert it to a UTC instant."""
    if not isinstance(value, datetime):
        raise ValueError("A valid local date and time is required.")

    if value.tzinfo is not None:
        return value.astimezone(UTC)

    zone = timezone_from_name(timezone_name or user_timezone_name())
    local_value = value.replace(tzinfo=zone, fold=0)
    utc_value = local_value.astimezone(UTC)

    # During the spring DST transition, some local wall times do not exist.
    # Reject them instead of silently scheduling the reminder at another hour.
    round_trip = utc_value.astimezone(zone).replace(tzinfo=None)

    if round_trip != value:
        raise ValueError(
            "Ora aleasă nu există în fusul orar selectat din cauza schimbării "
            "orei de vară. Alege o altă oră."
        )

    return utc_value
