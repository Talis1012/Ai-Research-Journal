create extension if not exists pg_trgm with schema extensions;

-- Evaluate the authenticated user once per statement instead of once per row.
do $$
declare
    table_name text;
begin
    foreach table_name in array array[
        'projects',
        'chats',
        'messages',
        'experiment_ai_messages',
        'audio_records',
        'summaries',
        'project_ideas',
        'mindmap_nodes',
        'mindmap_edges',
        'mindmap_source_state',
        'library_folders',
        'library_items',
        'library_tags',
        'library_item_tags',
        'library_item_projects',
        'analysis_runs',
        'project_discovery_sets',
        'project_discovery_set_papers',
        'manuscripts',
        'manuscript_sections',
        'manuscript_sources',
        'manuscript_evidence',
        'manuscript_citations',
        'manuscript_versions',
        'manuscript_version_comments',
        'manuscript_submission_profiles',
        'manuscript_ai_messages',
        'manuscript_ai_contexts',
        'manuscript_assets'
    ]
    loop
        execute format(
            'drop policy if exists %I on public.%I',
            table_name || '_owner_access',
            table_name
        );
        execute format(
            'create policy %I on public.%I for all to authenticated '
            || 'using (user_id = (select app_private.current_app_user_id())) '
            || 'with check (user_id = (select app_private.current_app_user_id()))',
            table_name || '_owner_access',
            table_name
        );
    end loop;
end;
$$;

drop policy if exists research_storage_select_own on storage.objects;
drop policy if exists research_storage_insert_own on storage.objects;
drop policy if exists research_storage_update_own on storage.objects;
drop policy if exists research_storage_delete_own on storage.objects;

create policy research_storage_select_own
on storage.objects for select to authenticated
using (
    bucket_id in ('audio', 'library', 'analysis-artifacts', 'manuscript-assets')
    and (storage.foldername(name))[1] = 'users'
    and (storage.foldername(name))[2] =
        (select app_private.current_app_user_id())::text
);

create policy research_storage_insert_own
on storage.objects for insert to authenticated
with check (
    bucket_id in ('audio', 'library', 'analysis-artifacts', 'manuscript-assets')
    and (storage.foldername(name))[1] = 'users'
    and (storage.foldername(name))[2] =
        (select app_private.current_app_user_id())::text
);

create policy research_storage_update_own
on storage.objects for update to authenticated
using (
    bucket_id in ('audio', 'library', 'analysis-artifacts', 'manuscript-assets')
    and (storage.foldername(name))[1] = 'users'
    and (storage.foldername(name))[2] =
        (select app_private.current_app_user_id())::text
)
with check (
    bucket_id in ('audio', 'library', 'analysis-artifacts', 'manuscript-assets')
    and (storage.foldername(name))[1] = 'users'
    and (storage.foldername(name))[2] =
        (select app_private.current_app_user_id())::text
);

create policy research_storage_delete_own
on storage.objects for delete to authenticated
using (
    bucket_id in ('audio', 'library', 'analysis-artifacts', 'manuscript-assets')
    and (storage.foldername(name))[1] = 'users'
    and (storage.foldername(name))[2] =
        (select app_private.current_app_user_id())::text
);

create index if not exists idx_projects_user_created
    on public.projects(user_id, created_at desc, id desc);
create index if not exists idx_chats_user_project_created
    on public.chats(user_id, project_id, created_at desc, id desc);
create index if not exists idx_messages_user_chat_created
    on public.messages(user_id, chat_id, created_at desc, id desc);
create index if not exists idx_experiment_ai_messages_user_chat_created
    on public.experiment_ai_messages(user_id, chat_id, created_at desc, id desc);
create index if not exists idx_audio_records_user_chat_created
    on public.audio_records(user_id, chat_id, created_at desc, id desc);
create index if not exists idx_project_ideas_user_project_created
    on public.project_ideas(user_id, project_id, created_at desc, id desc);
create index if not exists idx_mindmap_edges_user_project
    on public.mindmap_edges(user_id, project_id, id);
create index if not exists idx_library_items_user_created
    on public.library_items(user_id, created_at desc, id desc);
create index if not exists idx_library_items_user_title
    on public.library_items(user_id, title);
create index if not exists idx_library_items_title_trgm
    on public.library_items using gin (title extensions.gin_trgm_ops);
create index if not exists idx_library_items_authors_trgm
    on public.library_items using gin (authors extensions.gin_trgm_ops);
create index if not exists idx_library_item_projects_user_project
    on public.library_item_projects(user_id, project_id, item_id);
create index if not exists idx_manuscript_sources_user_manuscript
    on public.manuscript_sources(user_id, manuscript_id, library_item_id);
create index if not exists idx_manuscript_ai_messages_user_manuscript_created
    on public.manuscript_ai_messages(
        user_id,
        manuscript_id,
        created_at,
        id
    );

analyze public.projects;
analyze public.chats;
analyze public.messages;
analyze public.library_items;
analyze public.manuscripts;
analyze public.manuscript_sections;
analyze public.manuscript_versions;
