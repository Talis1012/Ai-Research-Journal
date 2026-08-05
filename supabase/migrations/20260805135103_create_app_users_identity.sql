create schema if not exists app_private;

revoke all on schema app_private from public;
grant usage on schema app_private to authenticated;

create table public.app_users (
    id uuid primary key default gen_random_uuid(),
    auth_issuer text not null,
    auth_subject text not null,
    email text,
    display_name text,
    avatar_url text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),

    constraint app_users_auth_identity_key
        unique (auth_issuer, auth_subject),
    constraint app_users_auth_issuer_not_blank
        check (btrim(auth_issuer) <> ''),
    constraint app_users_auth_subject_not_blank
        check (btrim(auth_subject) <> '')
);

comment on table public.app_users is
    'Application identities mapped from the trusted Auth0 iss and sub claims.';
comment on column public.app_users.auth_issuer is
    'Normalized Auth0 issuer without a trailing slash.';
comment on column public.app_users.auth_subject is
    'Stable Auth0 subject identifier. Email is never used as identity.';

create function app_private.set_updated_at()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
    new.updated_at := now();
    return new;
end;
$$;

create trigger app_users_set_updated_at
before update on public.app_users
for each row
execute function app_private.set_updated_at();

create function app_private.current_app_user_id()
returns uuid
language sql
stable
security definer
set search_path = ''
as $$
    select app_user.id
    from public.app_users as app_user
    where app_user.auth_issuer = nullif(
        rtrim(btrim(coalesce(auth.jwt() ->> 'iss', '')), '/'),
        ''
    )
      and app_user.auth_subject = nullif(
        btrim(coalesce(auth.jwt() ->> 'sub', '')),
        ''
      )
    limit 1
$$;

comment on function app_private.current_app_user_id() is
    'Resolves the application user from verified Auth0 JWT iss and sub claims.';

revoke all on function app_private.current_app_user_id() from public;
grant execute on function app_private.current_app_user_id() to authenticated;

create function public.ensure_current_app_user()
returns uuid
language plpgsql
security definer
set search_path = ''
as $$
declare
    claims jsonb := auth.jwt();
    normalized_issuer text;
    normalized_subject text;
    claim_email text;
    claim_display_name text;
    claim_avatar_url text;
    resolved_user_id uuid;
begin
    if coalesce(claims ->> 'role', '') <> 'authenticated' then
        raise exception 'An authenticated Auth0 identity is required.'
            using errcode = '42501';
    end if;

    normalized_issuer := nullif(
        rtrim(btrim(coalesce(claims ->> 'iss', '')), '/'),
        ''
    );
    normalized_subject := nullif(
        btrim(coalesce(claims ->> 'sub', '')),
        ''
    );

    if normalized_issuer is null or normalized_subject is null then
        raise exception 'The Auth0 token must include non-empty iss and sub claims.'
            using errcode = '22023';
    end if;

    claim_email := nullif(btrim(coalesce(claims ->> 'email', '')), '');
    claim_display_name := nullif(
        btrim(
            coalesce(
                claims ->> 'name',
                claims ->> 'nickname',
                claims ->> 'preferred_username',
                ''
            )
        ),
        ''
    );
    claim_avatar_url := nullif(btrim(coalesce(claims ->> 'picture', '')), '');

    insert into public.app_users (
        auth_issuer,
        auth_subject,
        email,
        display_name,
        avatar_url
    )
    values (
        normalized_issuer,
        normalized_subject,
        claim_email,
        claim_display_name,
        claim_avatar_url
    )
    on conflict (auth_issuer, auth_subject)
    do update set
        email = coalesce(excluded.email, app_users.email),
        display_name = coalesce(excluded.display_name, app_users.display_name),
        avatar_url = coalesce(excluded.avatar_url, app_users.avatar_url)
    returning id into resolved_user_id;

    return resolved_user_id;
end;
$$;

comment on function public.ensure_current_app_user() is
    'Creates or refreshes the current application profile from a verified Auth0 ID token.';

revoke all on function public.ensure_current_app_user() from public;
grant execute on function public.ensure_current_app_user() to authenticated;

alter table public.app_users enable row level security;
alter table public.app_users force row level security;

create policy app_users_select_own
on public.app_users
for select
to authenticated
using (id = app_private.current_app_user_id());

revoke all on table public.app_users from anon;
revoke all on table public.app_users from authenticated;
grant select on table public.app_users to authenticated;
