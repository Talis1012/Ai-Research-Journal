drop policy if exists app_users_select_own on public.app_users;

create policy app_users_select_own
on public.app_users
for select
to authenticated
using (
    auth_issuer = nullif(
        rtrim(btrim(coalesce(auth.jwt() ->> 'iss', '')), '/'),
        ''
    )
    and auth_subject = nullif(
        btrim(coalesce(auth.jwt() ->> 'sub', '')),
        ''
    )
);

create policy app_users_insert_own
on public.app_users
for insert
to authenticated
with check (
    auth_issuer = nullif(
        rtrim(btrim(coalesce(auth.jwt() ->> 'iss', '')), '/'),
        ''
    )
    and auth_subject = nullif(
        btrim(coalesce(auth.jwt() ->> 'sub', '')),
        ''
    )
);

create policy app_users_update_own
on public.app_users
for update
to authenticated
using (
    auth_issuer = nullif(
        rtrim(btrim(coalesce(auth.jwt() ->> 'iss', '')), '/'),
        ''
    )
    and auth_subject = nullif(
        btrim(coalesce(auth.jwt() ->> 'sub', '')),
        ''
    )
)
with check (
    auth_issuer = nullif(
        rtrim(btrim(coalesce(auth.jwt() ->> 'iss', '')), '/'),
        ''
    )
    and auth_subject = nullif(
        btrim(coalesce(auth.jwt() ->> 'sub', '')),
        ''
    )
);

alter function app_private.current_app_user_id() security invoker;
alter function public.ensure_current_app_user() security invoker;

revoke all on function app_private.set_updated_at() from public;
revoke all on function app_private.set_updated_at() from anon;
revoke all on function app_private.set_updated_at() from authenticated;

revoke all on function app_private.current_app_user_id() from public;
revoke all on function app_private.current_app_user_id() from anon;
revoke all on function app_private.current_app_user_id() from authenticated;
grant execute on function app_private.current_app_user_id() to authenticated;

revoke all on function public.ensure_current_app_user() from public;
revoke all on function public.ensure_current_app_user() from anon;
revoke all on function public.ensure_current_app_user() from authenticated;
grant execute on function public.ensure_current_app_user() to authenticated;

revoke all on table public.app_users from anon;
revoke all on table public.app_users from authenticated;

grant select on table public.app_users to authenticated;
grant insert (
    auth_issuer,
    auth_subject,
    email,
    display_name,
    avatar_url
) on public.app_users to authenticated;
grant update (
    email,
    display_name,
    avatar_url
) on public.app_users to authenticated;
