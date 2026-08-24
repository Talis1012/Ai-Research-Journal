alter table public.calendar_reminders
    add column timezone_name text;

-- The original schema did not retain the browser timezone. Preserve the exact
-- instant used by the old UTC-based notification poller instead of guessing a
-- region and potentially moving existing reminders.
update public.calendar_reminders
set timezone_name = 'UTC'
where timezone_name is null;

alter table public.calendar_reminders
    alter column reminder_at type timestamptz
    using reminder_at at time zone 'UTC';

alter table public.calendar_reminders
    alter column timezone_name set default 'UTC',
    alter column timezone_name set not null;

alter table public.calendar_reminders
    add constraint calendar_reminders_timezone_name_not_empty
    check (btrim(timezone_name) <> '');
