-- Library uploads are validated by the application and include several MIME
-- variants emitted by browsers (including application/octet-stream). Keep the
-- bucket private and retain the strict per-object size limit without rejecting
-- legitimate document types by MIME label alone.
update storage.buckets
set allowed_mime_types = null
where id = 'library';

create function public.delete_current_workspace()
returns void
language plpgsql
security definer
set search_path = ''
as $$
declare
    claims jsonb := auth.jwt();
    resolved_user_id uuid;
begin
    if coalesce(claims ->> 'role', '') <> 'authenticated' then
        raise exception 'An authenticated identity is required.'
            using errcode = '42501';
    end if;

    select app_user.id
    into resolved_user_id
    from public.app_users as app_user
    where app_user.auth_issuer = nullif(
        rtrim(btrim(coalesce(claims ->> 'iss', '')), '/'),
        ''
    )
      and app_user.auth_subject = nullif(
        btrim(coalesce(claims ->> 'sub', '')),
        ''
      )
    limit 1;

    if resolved_user_id is null then
        return;
    end if;

    delete from app_private.usage_counters
    where principal = resolved_user_id::text;

    delete from app_private.resource_leases
    where principal = resolved_user_id::text;

    delete from public.app_users
    where id = resolved_user_id;
end;
$$;

revoke all on function public.delete_current_workspace() from public;
revoke all on function public.delete_current_workspace() from anon;
revoke all on function public.delete_current_workspace() from authenticated;
grant execute on function public.delete_current_workspace() to authenticated;
