import calendar as month_calendar
from collections import defaultdict
from datetime import date, datetime, time, timedelta

import streamlit as st

from db.calendar_queries import (
    create_calendar_reminder,
    delete_calendar_reminder,
    get_calendar_reminders,
    get_upcoming_calendar_reminders,
    set_calendar_reminder_completed,
)
from db.database import init_db_once
from utils.auth import require_auth
from utils.query_cache import cached_read
from utils.ui import (
    header_icons,
    load_css,
    render_due_reminder_notifications,
    render_html,
    safe_html,
    sidebar_nav,
    top_brand,
)


st.set_page_config(
    page_title="Calendar · Research Journal AI",
    page_icon="📅",
    layout="wide",
)

require_auth()
init_db_once(st.session_state)
load_css()
render_due_reminder_notifications()


ROMANIAN_MONTHS = (
    "",
    "Ianuarie",
    "Februarie",
    "Martie",
    "Aprilie",
    "Mai",
    "Iunie",
    "Iulie",
    "August",
    "Septembrie",
    "Octombrie",
    "Noiembrie",
    "Decembrie",
)

ROMANIAN_WEEKDAYS = ("LUN", "MAR", "MIE", "JOI", "VIN", "SÂM", "DUM")


def reminder_datetime(value) -> datetime:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)

    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(
        tzinfo=None
    )


def month_start(value: date) -> date:
    return value.replace(day=1)


def shifted_month(value: date, offset: int) -> date:
    month_index = value.year * 12 + value.month - 1 + offset
    return date(month_index // 12, month_index % 12 + 1, 1)


def matching_date_in_month(value: date, day_number: int) -> date:
    last_day = month_calendar.monthrange(value.year, value.month)[1]
    return value.replace(day=min(max(1, int(day_number)), last_day))


def next_quarter_hour(value: datetime) -> time:
    rounded = value.replace(second=0, microsecond=0)
    minutes_to_add = (15 - rounded.minute % 15) % 15

    if minutes_to_add == 0:
        minutes_to_add = 15

    return (rounded + timedelta(minutes=minutes_to_add)).time()


def formatted_long_date(value: date) -> str:
    return f"{value.day} {ROMANIAN_MONTHS[value.month].lower()} {value.year}"


def render_page_css():
    render_html(
        """
        <style>
        .calendar-page-scope,
        .calendar-context-scope,
        .calendar-grid-scope,
        .calendar-side-scope {
            display: none;
        }

        div[data-testid="column"]:has(.calendar-page-scope) {
            min-height: calc(100vh - var(--topbar-h));
            padding: 22px 26px 42px !important;
            background: #f9fbfe;
        }

        div[data-testid="column"]:has(.calendar-page-scope)
        > div[data-testid="stVerticalBlock"] {
            gap: 0.8rem;
        }

        .calendar-context {
            min-height: var(--topbar-h);
            display: flex;
            align-items: center;
            gap: 10px;
            color: #344054;
            font-size: 0.88rem;
            font-weight: 780;
        }

        .calendar-context-icon {
            width: 32px;
            height: 32px;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            border: 1px solid #d7e4f3;
            border-radius: 8px;
            background: #f2f7ff;
            color: #1769d2;
            font-size: 1rem;
        }

        .calendar-heading {
            color: #101828;
            font-size: 1.85rem;
            font-weight: 880;
            line-height: 1.08;
            padding-top: 4px;
        }

        .calendar-subtitle {
            color: #667085;
            font-size: 0.88rem;
            margin-top: 7px;
        }

        div[class*="st-key-calendar_month_card"],
        div[class*="st-key-calendar_side_panel"] {
            border: 1px solid #dfe6ef !important;
            border-radius: 12px !important;
            background: #ffffff !important;
            box-shadow: 0 10px 28px rgba(16, 24, 40, 0.045) !important;
        }

        div[class*="st-key-calendar_month_card"] {
            padding: 18px 18px 20px !important;
        }

        div[class*="st-key-calendar_side_panel"] {
            min-height: 665px;
            padding: 18px !important;
        }

        div[class*="st-key-calendar_month_card"]
        > div[data-testid="stVerticalBlock"] {
            gap: 0.55rem;
        }

        .calendar-month-title {
            color: #101828;
            font-size: 1.12rem;
            font-weight: 860;
            text-align: center;
            line-height: 2.35rem;
        }

        .calendar-weekday {
            color: #8a95a8;
            font-size: 0.68rem;
            font-weight: 850;
            letter-spacing: 0.08em;
            text-align: center;
            padding: 7px 0 5px;
        }

        .calendar-empty-day {
            min-height: 88px;
            border: 1px solid transparent;
        }

        div[class*="st-key-calendar_day_"] button {
            min-height: 88px !important;
            height: 88px !important;
            justify-content: flex-start !important;
            align-items: flex-start !important;
            padding: 10px 11px !important;
            border: 1px solid #e2e8f0 !important;
            border-radius: 9px !important;
            background: #ffffff !important;
            color: #344054 !important;
            box-shadow: none !important;
        }

        div[class*="st-key-calendar_day_"] button p {
            width: 100%;
            color: inherit !important;
            font-size: 0.76rem !important;
            line-height: 1.5 !important;
            text-align: left !important;
        }

        div[class*="st-key-calendar_day_"] button strong {
            color: #101828;
            font-size: 0.88rem;
            font-weight: 850;
        }

        div[class*="st-key-calendar_day_"] button:hover {
            border-color: #b8d4f7 !important;
            background: #f7fbff !important;
            color: #1769d2 !important;
        }

        div[class*="st-key-calendar_day_today_"] button {
            border-color: #8db9ee !important;
            box-shadow: inset 0 0 0 1px #8db9ee !important;
        }

        div[class*="st-key-calendar_day_selected_"] button {
            border-color: #1769d2 !important;
            background: #eaf3ff !important;
            color: #145fc4 !important;
            box-shadow: inset 0 0 0 1px #1769d2 !important;
        }

        div[class*="st-key-calendar_day_selected_"] button strong {
            color: #145fc4 !important;
        }

        .calendar-panel-eyebrow {
            color: #1769d2;
            font-size: 0.68rem;
            font-weight: 850;
            letter-spacing: 0.08em;
            text-transform: uppercase;
        }

        .calendar-panel-title {
            color: #101828;
            font-size: 1.02rem;
            font-weight: 860;
            line-height: 1.35;
            margin-top: 4px;
        }

        .calendar-panel-caption {
            color: #667085;
            font-size: 0.74rem;
            line-height: 1.45;
            margin-top: 3px;
        }

        div[class*="st-key-calendar_reminder_card_"] {
            border: 1px solid #e0e7f0 !important;
            border-left: 4px solid #1769d2 !important;
            border-radius: 9px !important;
            background: #fbfdff !important;
            padding: 11px 11px 9px !important;
            margin-top: 4px !important;
        }

        div[class*="st-key-calendar_reminder_card_done_"] {
            border-left-color: #8a95a8 !important;
            background: #f7f8fa !important;
            opacity: 0.78;
        }

        .calendar-reminder-time {
            color: #1769d2;
            font-size: 0.72rem;
            font-weight: 850;
            letter-spacing: 0.03em;
        }

        .calendar-reminder-title {
            color: #101828;
            font-size: 0.86rem;
            font-weight: 830;
            line-height: 1.35;
            margin-top: 3px;
            overflow-wrap: anywhere;
        }

        .calendar-reminder-notes {
            color: #667085;
            font-size: 0.72rem;
            line-height: 1.45;
            margin: 4px 0 2px;
            overflow-wrap: anywhere;
        }

        div[class*="st-key-calendar_reminder_card_done_"]
        .calendar-reminder-title {
            text-decoration: line-through;
        }

        div[class*="st-key-calendar_action_"] button {
            min-height: 31px !important;
            padding: 4px 8px !important;
            font-size: 0.68rem !important;
        }

        .calendar-empty-state {
            min-height: 155px;
            border: 1px dashed #ccd8e7;
            border-radius: 10px;
            background: #fbfdff;
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            text-align: center;
            color: #667085;
            font-size: 0.76rem;
            line-height: 1.45;
            padding: 20px;
            margin-top: 8px;
        }

        .calendar-empty-icon {
            width: 42px;
            height: 42px;
            border-radius: 10px;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            background: #eaf3ff;
            color: #1769d2;
            font-size: 1.25rem;
            font-weight: 900;
            margin-bottom: 9px;
        }

        .calendar-upcoming-title {
            color: #101828;
            font-size: 0.82rem;
            font-weight: 850;
            margin: 2px 0 6px;
        }

        .calendar-upcoming-row {
            display: grid;
            grid-template-columns: 42px 1fr;
            gap: 9px;
            align-items: center;
            padding: 8px 0;
            border-bottom: 1px solid #edf1f6;
        }

        .calendar-upcoming-date {
            width: 42px;
            min-height: 40px;
            border-radius: 8px;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            background: #edf5ff;
            color: #1769d2;
            font-size: 0.64rem;
            font-weight: 820;
            line-height: 1.15;
        }

        .calendar-upcoming-date strong {
            font-size: 0.88rem;
        }

        .calendar-upcoming-name {
            color: #344054;
            font-size: 0.76rem;
            font-weight: 780;
            line-height: 1.35;
            overflow-wrap: anywhere;
        }

        .calendar-upcoming-time {
            color: #8a95a8;
            font-size: 0.67rem;
            margin-top: 2px;
        }

        @media (max-width: 1100px) {
            div[class*="st-key-calendar_side_panel"] {
                min-height: auto;
            }

            div[class*="st-key-calendar_day_"] button,
            .calendar-empty-day {
                min-height: 74px !important;
                height: 74px !important;
            }
        }
        </style>
        """
    )


@st.dialog("Reminder nou", width="small")
def render_new_reminder_dialog(default_date: date):
    render_html(
        """
        <div style="color:#667085;font-size:.82rem;line-height:1.5;margin-bottom:8px;">
            Alege momentul în care vrei să primești notificarea.
        </div>
        """
    )

    with st.form("calendar_create_reminder_form", clear_on_submit=False):
        title = st.text_input(
            "Titlu",
            placeholder="Ex: Verifică rezultatele experimentului",
            max_chars=160,
        )
        date_col, time_col = st.columns(2, gap="small")

        with date_col:
            reminder_date = st.date_input(
                "Data",
                value=default_date,
                format="DD.MM.YYYY",
            )

        with time_col:
            reminder_time = st.time_input(
                "Ora",
                value=next_quarter_hour(datetime.now()),
                step=900,
            )

        notes = st.text_area(
            "Notițe (opțional)",
            placeholder="Adaugă un detaliu scurt…",
            max_chars=2000,
            height=100,
        )
        submitted = st.form_submit_button(
            "Salvează reminder-ul",
            icon=":material/notifications_active:",
            type="primary",
            width="stretch",
        )

    if not submitted:
        return

    try:
        reminder_id = create_calendar_reminder(
            title,
            datetime.combine(reminder_date, reminder_time),
            notes,
        )
    except ValueError as exc:
        st.error(str(exc))
        return

    st.session_state["calendar_selected_date"] = reminder_date.isoformat()
    st.session_state["calendar_active_month"] = month_start(
        reminder_date
    ).isoformat()
    st.session_state["calendar_last_created_id"] = reminder_id
    st.toast("Reminder salvat.", icon=":material/check_circle:")
    st.rerun()


def render_reminder_card(reminder: dict):
    due_at = reminder_datetime(reminder["reminder_at"])
    completed = bool(reminder["completed"])
    state = "done" if completed else "open"

    with st.container(key=f"calendar_reminder_card_{state}_{reminder['id']}"):
        render_html(
            f"""
            <div class="calendar-reminder-time">{due_at.strftime('%H:%M')}</div>
            <div class="calendar-reminder-title">{safe_html(reminder['title'])}</div>
            {
                f'<div class="calendar-reminder-notes">{safe_html(reminder["notes"])}</div>'
                if reminder.get("notes")
                else ""
            }
            """
        )
        done_col, delete_col = st.columns(2, gap="small")

        with done_col:
            with st.container(key=f"calendar_action_done_{reminder['id']}"):
                if st.button(
                    "Redeschide" if completed else "Gata",
                    icon=(
                        ":material/undo:"
                        if completed
                        else ":material/check_circle:"
                    ),
                    key=f"calendar_toggle_{reminder['id']}",
                    width="stretch",
                ):
                    set_calendar_reminder_completed(reminder["id"], not completed)
                    st.rerun()

        with delete_col:
            with st.container(key=f"calendar_action_delete_{reminder['id']}"):
                if st.button(
                    "Șterge",
                    icon=":material/delete_outline:",
                    key=f"calendar_delete_{reminder['id']}",
                    width="stretch",
                ):
                    delete_calendar_reminder(reminder["id"])
                    st.toast("Reminder șters.")
                    st.rerun()


def render_upcoming_reminders(reminders: list[dict]):
    render_html('<div class="calendar-upcoming-title">Urmează</div>')

    if not reminders:
        render_html(
            '<div class="calendar-panel-caption">Nu mai ai alte remindere programate.</div>'
        )
        return

    for reminder in reminders[:6]:
        due_at = reminder_datetime(reminder["reminder_at"])
        month_short = ROMANIAN_MONTHS[due_at.month][:3].upper()
        render_html(
            f"""
            <div class="calendar-upcoming-row">
                <div class="calendar-upcoming-date">
                    <strong>{due_at.day}</strong>
                    <span>{month_short}</span>
                </div>
                <div>
                    <div class="calendar-upcoming-name">{safe_html(reminder['title'])}</div>
                    <div class="calendar-upcoming-time">{due_at.strftime('%H:%M')}</div>
                </div>
            </div>
            """
        )


render_page_css()
today = date.today()
st.session_state.setdefault("calendar_active_month", month_start(today).isoformat())
st.session_state.setdefault("calendar_selected_date", today.isoformat())

try:
    active_month = month_start(
        date.fromisoformat(st.session_state["calendar_active_month"])
    )
except (TypeError, ValueError):
    active_month = month_start(today)
    st.session_state["calendar_active_month"] = active_month.isoformat()

try:
    selected_date = date.fromisoformat(st.session_state["calendar_selected_date"])
except (TypeError, ValueError):
    selected_date = today
    st.session_state["calendar_selected_date"] = selected_date.isoformat()

next_month = shifted_month(active_month, 1)
month_reminders = cached_read(
    get_calendar_reminders,
    datetime.combine(active_month, time.min),
    datetime.combine(next_month, time.min),
)
reminders_by_date: dict[date, list[dict]] = defaultdict(list)

for reminder in month_reminders:
    reminders_by_date[reminder_datetime(reminder["reminder_at"]).date()].append(reminder)

upcoming_reminders = cached_read(
    get_upcoming_calendar_reminders,
    datetime.now().replace(second=0, microsecond=0),
    8,
)

top_brand_col, top_context_col, top_space_col, top_user_col = st.columns(
    [1.25, 2.8, 1.9, 1.65],
    gap="large",
)

with top_brand_col:
    top_brand()

with top_context_col:
    render_html(
        """
        <div class="calendar-context-scope"></div>
        <div class="calendar-context">
            <span class="calendar-context-icon">▦</span>
            <span>Planificator personal de cercetare</span>
        </div>
        """
    )

with top_space_col:
    render_html('<div class="top-search-scope"></div>')

with top_user_col:
    render_html('<div class="top-user-scope"></div>')
    header_icons()

nav_col, page_col = st.columns([1.05, 6.48], gap="small")

with nav_col:
    render_html('<div class="nav-panel-scope"></div>')
    sidebar_nav("calendar")

with page_col:
    render_html('<div class="calendar-page-scope"></div>')
    heading_col, action_col = st.columns([3.2, 0.9], gap="large")

    with heading_col:
        render_html(
            """
            <div class="calendar-heading">Calendar</div>
            <div class="calendar-subtitle">Planifică reminder-e și păstrează momentele importante la vedere.</div>
            """
        )

    with action_col:
        if st.button(
            "Reminder nou",
            icon=":material/add_alarm:",
            type="primary",
            width="stretch",
            key="calendar_new_reminder_header",
        ):
            render_new_reminder_dialog(selected_date)

    calendar_col, side_col = st.columns([3.65, 1.45], gap="small")

    with calendar_col:
        with st.container(key="calendar_month_card"):
            render_html('<div class="calendar-grid-scope"></div>')
            prev_col, month_col, today_col, next_col = st.columns(
                [0.48, 2.7, 0.72, 0.48],
                gap="small",
                vertical_alignment="center",
            )

            with prev_col:
                if st.button(
                    "‹",
                    help="Luna anterioară",
                    key="calendar_previous_month",
                    width="stretch",
                ):
                    active_month = shifted_month(active_month, -1)
                    st.session_state["calendar_active_month"] = active_month.isoformat()
                    st.session_state["calendar_selected_date"] = matching_date_in_month(
                        active_month,
                        selected_date.day,
                    ).isoformat()
                    st.rerun()

            with month_col:
                render_html(
                    f'<div class="calendar-month-title">{ROMANIAN_MONTHS[active_month.month]} {active_month.year}</div>'
                )

            with today_col:
                if st.button(
                    "Astăzi",
                    key="calendar_go_today",
                    width="stretch",
                ):
                    st.session_state["calendar_active_month"] = month_start(
                        today
                    ).isoformat()
                    st.session_state["calendar_selected_date"] = today.isoformat()
                    st.rerun()

            with next_col:
                if st.button(
                    "›",
                    help="Luna următoare",
                    key="calendar_next_month",
                    width="stretch",
                ):
                    active_month = shifted_month(active_month, 1)
                    st.session_state["calendar_active_month"] = active_month.isoformat()
                    st.session_state["calendar_selected_date"] = matching_date_in_month(
                        active_month,
                        selected_date.day,
                    ).isoformat()
                    st.rerun()

            weekday_columns = st.columns(7, gap="small")

            for weekday_col, weekday in zip(weekday_columns, ROMANIAN_WEEKDAYS):
                with weekday_col:
                    render_html(f'<div class="calendar-weekday">{weekday}</div>')

            for week in month_calendar.monthcalendar(
                active_month.year,
                active_month.month,
            ):
                day_columns = st.columns(7, gap="small")

                for day_col, day_number in zip(day_columns, week):
                    with day_col:
                        if day_number == 0:
                            render_html('<div class="calendar-empty-day"></div>')
                            continue

                        day_value = date(
                            active_month.year,
                            active_month.month,
                            day_number,
                        )
                        reminders = reminders_by_date.get(day_value, [])
                        reminder_count = len(reminders)

                        if day_value == selected_date:
                            state = "selected"
                        elif day_value == today:
                            state = "today"
                        else:
                            state = "default"

                        day_label = f"**{day_number}**"

                        if reminder_count:
                            suffix = "reminder" if reminder_count == 1 else "remindere"
                            day_label += f"  \n🔵 {reminder_count} {suffix}"

                        with st.container(
                            key=f"calendar_day_{state}_{day_value.isoformat().replace('-', '_')}"
                        ):
                            if st.button(
                                day_label,
                                key=f"calendar_select_day_{day_value.isoformat()}",
                                width="stretch",
                            ):
                                st.session_state[
                                    "calendar_selected_date"
                                ] = day_value.isoformat()
                                st.rerun()

    with side_col:
        with st.container(key="calendar_side_panel"):
            render_html('<div class="calendar-side-scope"></div>')
            selected_day_reminders = reminders_by_date.get(selected_date, [])
            render_html(
                f"""
                <div class="calendar-panel-eyebrow">Zi selectată</div>
                <div class="calendar-panel-title">{safe_html(formatted_long_date(selected_date))}</div>
                <div class="calendar-panel-caption">
                    {len(selected_day_reminders)} {'reminder' if len(selected_day_reminders) == 1 else 'remindere'} programate
                </div>
                """
            )

            if st.button(
                "Adaugă pentru această zi",
                icon=":material/add:",
                width="stretch",
                key="calendar_new_reminder_selected_day",
            ):
                render_new_reminder_dialog(selected_date)

            if selected_day_reminders:
                for reminder in selected_day_reminders:
                    render_reminder_card(reminder)
            else:
                render_html(
                    """
                    <div class="calendar-empty-state">
                        <span class="calendar-empty-icon">!</span>
                        <strong style="color:#344054;">Zi liberă</strong>
                        <span>Adaugă un reminder ca să nu uiți următorul pas.</span>
                    </div>
                    """
                )

            st.divider()
            render_upcoming_reminders(upcoming_reminders)
