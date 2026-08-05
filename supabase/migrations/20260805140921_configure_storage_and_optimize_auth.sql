drop policy if exists app_users_select_own on public.app_users;
drop policy if exists app_users_insert_own on public.app_users;
drop policy if exists app_users_update_own on public.app_users;

create policy app_users_select_own
on public.app_users
for select
to authenticated
using (
    auth_issuer = nullif(
        rtrim(
            btrim(coalesce((select auth.jwt()) ->> 'iss', '')),
            '/'
        ),
        ''
    )
    and auth_subject = nullif(
        btrim(coalesce((select auth.jwt()) ->> 'sub', '')),
        ''
    )
);

create policy app_users_insert_own
on public.app_users
for insert
to authenticated
with check (
    auth_issuer = nullif(
        rtrim(
            btrim(coalesce((select auth.jwt()) ->> 'iss', '')),
            '/'
        ),
        ''
    )
    and auth_subject = nullif(
        btrim(coalesce((select auth.jwt()) ->> 'sub', '')),
        ''
    )
);

create policy app_users_update_own
on public.app_users
for update
to authenticated
using (
    auth_issuer = nullif(
        rtrim(
            btrim(coalesce((select auth.jwt()) ->> 'iss', '')),
            '/'
        ),
        ''
    )
    and auth_subject = nullif(
        btrim(coalesce((select auth.jwt()) ->> 'sub', '')),
        ''
    )
)
with check (
    auth_issuer = nullif(
        rtrim(
            btrim(coalesce((select auth.jwt()) ->> 'iss', '')),
            '/'
        ),
        ''
    )
    and auth_subject = nullif(
        btrim(coalesce((select auth.jwt()) ->> 'sub', '')),
        ''
    )
);

insert into storage.buckets (
    id,
    name,
    public,
    file_size_limit,
    allowed_mime_types
)
values
    (
        'audio',
        'audio',
        false,
        26214400,
        array['audio/wav', 'audio/x-wav']
    ),
    (
        'library',
        'library',
        false,
        26214400,
        array[
            'application/pdf',
            'application/json',
            'application/msword',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'text/csv',
            'text/plain',
            'text/tab-separated-values'
        ]
    ),
    (
        'analysis-artifacts',
        'analysis-artifacts',
        false,
        52428800,
        array['text/csv', 'text/markdown', 'text/plain']
    ),
    (
        'manuscript-assets',
        'manuscript-assets',
        false,
        52428800,
        array['image/png']
    )
on conflict (id)
do update set
    name = excluded.name,
    public = excluded.public,
    file_size_limit = excluded.file_size_limit,
    allowed_mime_types = excluded.allowed_mime_types;

create policy research_storage_select_own
on storage.objects
for select
to authenticated
using (
    bucket_id in (
        'audio',
        'library',
        'analysis-artifacts',
        'manuscript-assets'
    )
    and (storage.foldername(name))[1] = 'users'
    and (storage.foldername(name))[2] =
        app_private.current_app_user_id()::text
);

create policy research_storage_insert_own
on storage.objects
for insert
to authenticated
with check (
    bucket_id in (
        'audio',
        'library',
        'analysis-artifacts',
        'manuscript-assets'
    )
    and (storage.foldername(name))[1] = 'users'
    and (storage.foldername(name))[2] =
        app_private.current_app_user_id()::text
);

create policy research_storage_update_own
on storage.objects
for update
to authenticated
using (
    bucket_id in (
        'audio',
        'library',
        'analysis-artifacts',
        'manuscript-assets'
    )
    and (storage.foldername(name))[1] = 'users'
    and (storage.foldername(name))[2] =
        app_private.current_app_user_id()::text
)
with check (
    bucket_id in (
        'audio',
        'library',
        'analysis-artifacts',
        'manuscript-assets'
    )
    and (storage.foldername(name))[1] = 'users'
    and (storage.foldername(name))[2] =
        app_private.current_app_user_id()::text
);

create policy research_storage_delete_own
on storage.objects
for delete
to authenticated
using (
    bucket_id in (
        'audio',
        'library',
        'analysis-artifacts',
        'manuscript-assets'
    )
    and (storage.foldername(name))[1] = 'users'
    and (storage.foldername(name))[2] =
        app_private.current_app_user_id()::text
);
