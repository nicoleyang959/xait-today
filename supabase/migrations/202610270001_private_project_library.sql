-- Apply to a fresh Supabase Free project before enabling the optional library.
-- This migration contains no deployment identifiers or credentials.
begin;

create schema if not exists xait_private;
revoke all on schema xait_private from public, anon, authenticated;
grant usage on schema xait_private to authenticated;

create table xait_private.saved_projects (
  id uuid primary key,
  owner_id uuid not null references auth.users(id) on delete cascade,
  url_key text not null check (url_key ~ '^[0-9a-f]{64}$'),
  canonical_url text,
  url text,
  title text,
  source_id text,
  source_issue_date date,
  notes text,
  status text not null default 'to_research'
    check (status in ('to_research', 'tried', 'watching')),
  version bigint not null default 1 check (version > 0),
  created_at timestamptz not null default pg_catalog.clock_timestamp(),
  updated_at timestamptz not null default pg_catalog.clock_timestamp(),
  deleted_at timestamptz,
  constraint saved_projects_owner_url_unique unique (owner_id, url_key),
  constraint saved_projects_content_state check (
    (deleted_at is null and canonical_url is not null and url is not null
      and title is not null and notes is not null
      and pg_catalog.char_length(url) between 1 and 2048
      and pg_catalog.char_length(canonical_url) between 1 and 2048
      and pg_catalog.char_length(title) between 1 and 200
      and pg_catalog.char_length(notes) <= 5000)
    or
    (deleted_at is not null and canonical_url is null and url is null
      and title is null and source_id is null and source_issue_date is null
      and notes is null and status = 'to_research')
  )
);
create index saved_projects_owner_page on xait_private.saved_projects(owner_id, id);

-- Receipts keep only identities/digests/versions, never old notes or OAuth data.
-- Permanent receipts are bounded at 10,000 per owner; they are never expired or
-- pruned behind an offline client's back. New mutations then fail safely until
-- the operator and owner explicitly arrange a migration, while replay works.
create table xait_private.record_mutation_receipts (
  owner_id uuid not null references auth.users(id) on delete cascade,
  mutation_id uuid not null,
  request_digest text not null check (request_digest ~ '^[0-9a-f]{64}$'),
  result_record_id uuid,
  result_version bigint,
  result_status text not null check (result_status in ('applied', 'existing', 'conflict', 'deleted')),
  created_at timestamptz not null default pg_catalog.clock_timestamp(),
  primary key (owner_id, mutation_id)
);

alter table xait_private.saved_projects enable row level security;
alter table xait_private.saved_projects force row level security;
alter table xait_private.record_mutation_receipts enable row level security;
alter table xait_private.record_mutation_receipts force row level security;
create policy saved_projects_read_own on xait_private.saved_projects
  for select to authenticated using ((select auth.uid()) = owner_id);
create policy receipts_read_own on xait_private.record_mutation_receipts
  for select to authenticated using ((select auth.uid()) = owner_id);
-- Definer RPCs run as the project's postgres role. These owner predicates also
-- make FORCE RLS correct if that controlled role does not have BYPASSRLS.
create policy saved_projects_rpc_owner on xait_private.saved_projects
  for all to postgres using ((select auth.uid()) = owner_id)
  with check ((select auth.uid()) = owner_id);
create policy receipts_rpc_owner on xait_private.record_mutation_receipts
  for all to postgres using ((select auth.uid()) = owner_id)
  with check ((select auth.uid()) = owner_id);
revoke all on xait_private.saved_projects from public, anon, authenticated;
revoke all on xait_private.record_mutation_receipts from public, anon, authenticated;
grant select on xait_private.saved_projects to authenticated;
-- No INSERT/UPDATE/DELETE table grants. Writes must use the checked RPC.

create function xait_private.url_component_decode(p_value text)
returns text language plpgsql immutable strict set search_path = '' as $$
declare
  output bytea := ''::bytea;
  position integer := 1;
  piece text;
begin
  while position <= pg_catalog.char_length(p_value) loop
    piece := pg_catalog.substr(p_value, position, 1);
    if piece = '%' and pg_catalog.substr(p_value, position + 1, 2) ~ '^[0-9A-Fa-f]{2}$' then
      output := output || pg_catalog.decode(pg_catalog.substr(p_value, position + 1, 2), 'hex');
      position := position + 3;
    else
      output := output || pg_catalog.convert_to(piece, 'UTF8');
      position := position + 1;
    end if;
  end loop;
  return pg_catalog.convert_from(output, 'UTF8');
exception when character_not_in_repertoire then
  raise exception using errcode = '22023', message = 'invalid_url';
end;
$$;

create function xait_private.url_has_credentials(p_component text)
returns boolean language plpgsql immutable strict set search_path = '' as $$
declare
  probe text := p_component;
  pass integer;
begin
  for pass in 1..3 loop
    probe := pg_catalog.lower(xait_private.url_component_decode(pg_catalog.replace(probe,'+',' ')));
    if probe ~ '(^|[?&#/;])[^?&#/;:=]*(auth|credential|token|secret|password|cookie|session|signature|private[_-]?key|api[_-]?key)[^?&#/;:=]*[[:space:]]*[:=]'
        or probe ~ '(^|[?&#/;])(key|code|sig)[[:space:]]*[:=]' then
      return true;
    end if;
    exit when probe !~ '%[0-9a-f]{2}';
  end loop;
  return false;
end;
$$;

-- Deliberately conservative: no DNS request, redirect, decoding of paths,
-- fragment removal, semantic query sorting, or fuzzy project-name matching.
create function xait_private.canonical_project_url(p_url text)
returns text language plpgsql immutable strict set search_path = '' as $$
declare
  parts text[];
  authority text;
  host text;
  port_text text;
  port_number integer;
  address inet;
  scheme text;
  path text;
  query_text text;
  fragment_text text;
  query_piece text;
  key_text text;
  kept text[] := array[]::text[];
begin
  if pg_catalog.char_length(p_url) not between 1 and 2048
      or p_url ~ '[[:space:][:cntrl:]<>"`\\]'
      or p_url ~* '%(?:00|0a|0d)' then
    raise exception using errcode = '22023', message = 'invalid_url';
  end if;
  parts := pg_catalog.regexp_match(p_url,
    '^([A-Za-z][A-Za-z0-9+.-]*)://([^/?#]+)([^?#]*)(?:\?([^#]*))?(?:#(.*))?$');
  if parts is null or pg_catalog.lower(parts[1]) not in ('http', 'https') then
    raise exception using errcode = '22023', message = 'invalid_url';
  end if;
  scheme := pg_catalog.lower(parts[1]);
  authority := parts[2];
  if authority ~ '[@%]' then
    raise exception using errcode = '22023', message = 'invalid_url';
  end if;
  if authority like '[%' then
    parts := pg_catalog.regexp_match(authority, '^\[([0-9A-Fa-f:.]+)\](?::([0-9]+))?$');
    if parts is null then
      raise exception using errcode = '22023', message = 'invalid_url';
    end if;
    host := pg_catalog.lower(parts[1]);
    port_text := parts[2];
  else
    parts := pg_catalog.regexp_match(authority, '^([^:]+)(?::([0-9]+))?$');
    if parts is null then
      raise exception using errcode = '22023', message = 'invalid_url';
    end if;
    host := pg_catalog.lower(pg_catalog.rtrim(parts[1], '.'));
    port_text := parts[2];
  end if;
  if port_text is not null then
    if pg_catalog.char_length(port_text) > 5 then
      raise exception using errcode = '22023', message = 'invalid_url';
    end if;
    port_number := port_text::integer;
    if port_number not between 1 and 65535 then
      raise exception using errcode = '22023', message = 'invalid_url';
    end if;
  end if;
  if host = '' or host = 'localhost' or host ~ '\.(localhost|local|internal|lan|home)$'
      or host ~ '(^|\.)(localtest\.me|lvh\.me|nip\.io|sslip\.io|xip\.io)$'
      or host !~ '[.:]' or host ~ '^[0-9]+$' or host like '0x%' then
    raise exception using errcode = '22023', message = 'invalid_url';
  end if;
  if host ~ '^[0-9.]+$' and host !~ '^(0|[1-9][0-9]{0,2})(\.(0|[1-9][0-9]{0,2})){3}$' then
    raise exception using errcode = '22023', message = 'invalid_url';
  end if;
  begin
    address := host::inet;
  exception when invalid_text_representation then
    address := null;
  end;
  if address is not null then
    if (pg_catalog.family(address) = 4 and (
        address <<= inet '0.0.0.0/8' or address <<= inet '10.0.0.0/8'
        or address <<= inet '100.64.0.0/10' or address <<= inet '127.0.0.0/8'
        or address <<= inet '169.254.0.0/16' or address <<= inet '172.16.0.0/12'
        or address <<= inet '192.0.0.0/24' or address <<= inet '192.0.2.0/24'
        or address <<= inet '192.168.0.0/16' or address <<= inet '198.18.0.0/15'
        or address <<= inet '198.51.100.0/24' or address <<= inet '203.0.113.0/24'
        or address <<= inet '224.0.0.0/4' or address <<= inet '240.0.0.0/4'))
      or (pg_catalog.family(address) = 6 and (
        not (address <<= inet '2000::/3') or address <<= inet '2001::/23'
        or address <<= inet '2001:db8::/32' or address <<= inet '2002::/16'
        or address <<= inet '3fff::/20')) then
      raise exception using errcode = '22023', message = 'invalid_url';
    end if;
  elsif host ~ '^[0-9.]+$' or host !~ '^[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$'
      or host ~ '\.\.' then
    raise exception using errcode = '22023', message = 'invalid_url';
  end if;
  parts := pg_catalog.regexp_match(p_url,
    '^([A-Za-z][A-Za-z0-9+.-]*)://([^/?#]+)([^?#]*)(?:\?([^#]*))?(?:#(.*))?$');
  path := parts[3];
  query_text := parts[4];
  fragment_text := parts[5];
  if xait_private.url_has_credentials(coalesce(query_text,''))
      or xait_private.url_has_credentials(coalesce(fragment_text,'')) then
    raise exception using errcode = '22023', message = 'invalid_url';
  end if;
  if query_text is not null then
    foreach query_piece in array pg_catalog.string_to_array(query_text, '&') loop
      key_text := pg_catalog.lower(xait_private.url_component_decode(
        pg_catalog.split_part(query_piece, '=', 1)));
      if pg_catalog.replace(key_text, '+', ' ') = any (array[
        'access_token','api_key','apikey','auth','authorization','cookie','credential',
        'key','code','sig','password','refresh_token','secret','session','sessionid','signature','token']) then
        raise exception using errcode = '22023', message = 'invalid_url';
      end if;
      if not (key_text = any (array[
          'utm_source','utm_medium','utm_campaign','utm_term','utm_content','utm_id',
          'utm_source_platform','utm_creative_format','utm_marketing_tactic',
          'fbclid','gclid','dclid','msclkid','mc_cid','mc_eid'])) then
        kept := pg_catalog.array_append(kept, query_piece);
      end if;
    end loop;
  end if;
  if fragment_text is not null then
    foreach query_piece in array pg_catalog.string_to_array(pg_catalog.replace(fragment_text, '?', '&'), '&') loop
      key_text := pg_catalog.lower(xait_private.url_component_decode(
        pg_catalog.split_part(query_piece, '=', 1)));
      if pg_catalog.replace(key_text, '+', ' ') in ('key','code','sig','auth','token','secret','password','cookie','session','signature','credential') then
        raise exception using errcode = '22023', message = 'invalid_url';
      end if;
    end loop;
  end if;
  if pg_catalog.strpos(host, ':') > 0 then host := '[' || host || ']'; end if;
  if port_number is not null and not ((scheme = 'http' and port_number = 80)
      or (scheme = 'https' and port_number = 443)) then
    host := host || ':' || port_number::text;
  end if;
  query_text := pg_catalog.array_to_string(kept, '&');
  return scheme || '://' || host || path
    || case when query_text <> '' then '?' || query_text else '' end
    || case when fragment_text <> '' then '#' || fragment_text else '' end;
end;
$$;

create function xait_private.record_json(p_record xait_private.saved_projects)
returns jsonb language sql stable set search_path = '' as $$
  select pg_catalog.jsonb_build_object(
    'id', (p_record).id, 'url_key', (p_record).url_key,
    'canonical_url', (p_record).canonical_url, 'url', (p_record).url,
    'title', (p_record).title, 'source_id', (p_record).source_id,
    'source_issue_date', (p_record).source_issue_date, 'notes', (p_record).notes,
    'status', case when (p_record).deleted_at is null then (p_record).status
      else 'to_research' end, 'version', (p_record).version,
    'created_at', (p_record).created_at, 'updated_at', (p_record).updated_at,
    'deleted_at', (p_record).deleted_at);
$$;

create function public.list_my_records(p_account_id uuid, p_after_id uuid default null, p_limit integer default 100)
returns jsonb language plpgsql security definer set search_path = '' set timezone = 'UTC' as $$
declare
  caller uuid := auth.uid();
  rows_json jsonb;
  last_id uuid;
  more_rows boolean;
begin
  if caller is null then
    raise exception using errcode = '28000', message = 'authentication_required';
  end if;
  if p_account_id is distinct from caller then
    raise exception using errcode = '28000', message = 'account_changed';
  end if;
  if p_limit is null or p_limit not between 1 and 100 then
    raise exception using errcode = '22023', message = 'invalid_page_size';
  end if;
  select coalesce(pg_catalog.jsonb_agg(xait_private.record_json(page::xait_private.saved_projects) order by page.id), '[]'::jsonb),
         (array_agg(page.id order by page.id desc))[1]
    into rows_json, last_id
    from (select * from xait_private.saved_projects
      where owner_id = caller and (p_after_id is null or id > p_after_id)
      order by id limit p_limit) page;
  select exists (select 1 from xait_private.saved_projects
    where owner_id = caller and last_id is not null and id > last_id) into more_rows;
  return pg_catalog.jsonb_build_object('records', rows_json,
    'next_after', case when more_rows then last_id else null end);
end;
$$;

create function public.apply_record_mutation(
  p_account_id uuid, p_mutation_id uuid, p_record_id uuid, p_operation text,
  p_expected_version bigint, p_payload jsonb)
returns jsonb language plpgsql security definer set search_path = '' set timezone = 'UTC' as $$
declare
  caller uuid := auth.uid();
  current_row xait_private.saved_projects;
  receipt xait_private.record_mutation_receipts;
  request_hash text;
  canonical text;
  identity_hash text;
  supplied_url text;
  supplied_title text;
  supplied_notes text;
  supplied_status text;
  supplied_source text;
  supplied_issue date;
  result_kind text;
  moment timestamptz;
  key_name text;
  active_count bigint;
  identity_count bigint;
  receipt_count bigint;
begin
  if caller is null then
    raise exception using errcode = '28000', message = 'authentication_required';
  end if;
  if p_account_id is distinct from caller then
    raise exception using errcode = '28000', message = 'account_changed';
  end if;
  if p_mutation_id is null or p_record_id is null or p_operation is null
      or p_operation not in ('create','update','delete','restore')
      or p_expected_version is null or p_expected_version < 0
      or p_payload is null or pg_catalog.jsonb_typeof(p_payload) <> 'object'
      or pg_catalog.pg_column_size(p_payload) > 40000 then
    raise exception using errcode = '22023', message = 'invalid_mutation';
  end if;
  for key_name in select pg_catalog.jsonb_object_keys(p_payload) loop
    if key_name not in ('url','title','source_id','source_issue_date','notes','status','canonical_url') then
      raise exception using errcode = '22023', message = 'invalid_payload';
    end if;
  end loop;
  request_hash := pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(
    pg_catalog.jsonb_build_object('id',p_record_id,'operation',p_operation,
      'expected_version',p_expected_version,'payload',p_payload)::text,'UTF8')),'hex');
  -- Serialize one owner's count, identity, receipt and version decisions in the
  -- same transaction. A hash collision only serializes unrelated owners.
  perform pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(caller::text, 714218));
  select * into receipt from xait_private.record_mutation_receipts
    where owner_id = caller and mutation_id = p_mutation_id;
  if found then
    if receipt.request_digest <> request_hash then
      raise exception using errcode = '22023', message = 'mutation_id_reused';
    end if;
    select * into current_row from xait_private.saved_projects
      where owner_id = caller and id = receipt.result_record_id;
    return pg_catalog.jsonb_build_object('status',receipt.result_status,
      'applied_version',receipt.result_version,
      'record',case when current_row.id is null then null else xait_private.record_json(current_row) end);
  end if;

  if p_operation = 'delete' then
    if p_payload <> '{}'::jsonb then
      raise exception using errcode = '22023', message = 'invalid_payload';
    end if;
  else
    for key_name in select pg_catalog.jsonb_object_keys(p_payload) loop
      if key_name = 'source_issue_date' then
        if pg_catalog.jsonb_typeof(p_payload -> key_name) not in ('string','null') then
          raise exception using errcode = '22023', message = 'invalid_payload';
        end if;
      elsif key_name = 'source_id' then
        if pg_catalog.jsonb_typeof(p_payload -> key_name) not in ('string','null') then
          raise exception using errcode = '22023', message = 'invalid_payload';
        end if;
      elsif pg_catalog.jsonb_typeof(p_payload -> key_name) <> 'string' then
        raise exception using errcode = '22023', message = 'invalid_payload';
      end if;
    end loop;
    if p_payload ? 'url' then
      supplied_url := p_payload ->> 'url';
      canonical := xait_private.canonical_project_url(supplied_url);
      identity_hash := pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(canonical,'UTF8')),'hex');
    end if;
    if p_payload ? 'canonical_url' and (canonical is null or p_payload ->> 'canonical_url' <> canonical) then
      raise exception using errcode = '22023', message = 'invalid_canonical_url';
    end if;
    if p_payload ? 'title' then
      supplied_title := pg_catalog.btrim(p_payload ->> 'title');
      if pg_catalog.char_length(supplied_title) not between 1 and 200 then
        raise exception using errcode = '22023', message = 'invalid_title';
      end if;
    end if;
    if p_payload ? 'notes' then
      supplied_notes := p_payload ->> 'notes';
      if pg_catalog.char_length(supplied_notes) > 5000 then
        raise exception using errcode = '22023', message = 'notes_too_long';
      end if;
    end if;
    if p_payload ? 'status' then
      supplied_status := p_payload ->> 'status';
      if supplied_status not in ('to_research','tried','watching') then
        raise exception using errcode = '22023', message = 'invalid_status';
      end if;
    end if;
    if p_payload ? 'source_id' then
      supplied_source := p_payload ->> 'source_id';
      if supplied_source is not null and supplied_source not in (
        'manual','github-trending','weekly-high-stars','product-hunt','product-hunt-ranking') then
        raise exception using errcode = '22023', message = 'invalid_source';
      end if;
    end if;
    if p_payload ->> 'source_issue_date' is not null then
      if (p_payload ->> 'source_issue_date') !~ '^\d{4}-\d{2}-\d{2}$' then
        raise exception using errcode = '22023', message = 'invalid_issue_date';
      end if;
      begin
        supplied_issue := (p_payload ->> 'source_issue_date')::date;
      exception when invalid_datetime_format or datetime_field_overflow then
        raise exception using errcode = '22023', message = 'invalid_issue_date';
      end;
    end if;
  end if;

  select * into current_row from xait_private.saved_projects
    where owner_id = caller and id = p_record_id for update;
  if p_operation <> 'create' and current_row.id is null then
    -- A guessed id and a missing id have the same side-effect-free result.
    -- Do not create unbounded receipts for attacker-chosen nonexistent ids.
    return pg_catalog.jsonb_build_object('status','deleted',
      'applied_version',null,'record',null);
  end if;
  select pg_catalog.count(*) into receipt_count from xait_private.record_mutation_receipts
    where owner_id = caller;
  if receipt_count >= 10000 then
    raise exception using errcode = 'P0001', message = 'storage_limit_reached';
  end if;
  if p_operation = 'create' then
    if p_expected_version <> 0 or supplied_url is null or supplied_title is null then
      raise exception using errcode = '22023', message = 'invalid_create';
    end if;
    if current_row.id is not null and current_row.url_key <> identity_hash then
      raise exception using errcode = '22023', message = 'record_identity_immutable';
    end if;
    select * into current_row from xait_private.saved_projects
      where owner_id = caller and url_key = identity_hash for update;
    if found then
      result_kind := case when current_row.deleted_at is null then 'existing' else 'deleted' end;
    else
      -- Tombstones must remain to stop old devices resurrecting deleted data.
      -- Bound all identities as well as active rows, rather than pruning them.
      select pg_catalog.count(*) into identity_count from xait_private.saved_projects
        where owner_id = caller;
      if identity_count >= 5000 then
        raise exception using errcode = 'P0001', message = 'storage_limit_reached';
      end if;
      select pg_catalog.count(*) into active_count from xait_private.saved_projects
        where owner_id = caller and deleted_at is null;
      if active_count >= 1000 then
        raise exception using errcode = 'P0001', message = 'record_limit_reached';
      end if;
      moment := pg_catalog.clock_timestamp();
      begin
        insert into xait_private.saved_projects (
          id,owner_id,url_key,canonical_url,url,title,source_id,source_issue_date,
          notes,status,version,created_at,updated_at)
        values (p_record_id,caller,identity_hash,canonical,supplied_url,supplied_title,
          coalesce(supplied_source,'manual'),supplied_issue,coalesce(supplied_notes,''),
          coalesce(supplied_status,'to_research'),1,moment,moment)
        returning * into current_row;
      exception when unique_violation then
        raise exception using errcode = '22023', message = 'record_id_unavailable';
      end;
      result_kind := 'applied';
    end if;
  elsif p_expected_version <> current_row.version then
    result_kind := 'conflict';
  elsif p_operation <> 'restore' and current_row.deleted_at is not null then
    result_kind := 'deleted';
  elsif p_operation = 'restore' and current_row.deleted_at is null then
    result_kind := 'conflict';
  else
    moment := pg_catalog.clock_timestamp();
    if p_operation = 'delete' then
      update xait_private.saved_projects set canonical_url=null,url=null,title=null,
        source_id=null,source_issue_date=null,notes=null,status='to_research',deleted_at=moment,
        version=version+1,updated_at=moment
        where owner_id=caller and id=current_row.id returning * into current_row;
    elsif p_operation = 'restore' then
      if supplied_url is null or supplied_title is null or identity_hash <> current_row.url_key then
        raise exception using errcode='22023',message='invalid_restore';
      end if;
      select pg_catalog.count(*) into active_count from xait_private.saved_projects
        where owner_id=caller and deleted_at is null;
      if active_count >= 1000 then
        raise exception using errcode='P0001',message='record_limit_reached';
      end if;
      update xait_private.saved_projects set canonical_url=canonical,url=supplied_url,
        title=supplied_title,source_id=coalesce(supplied_source,'manual'),source_issue_date=supplied_issue,
        notes=coalesce(supplied_notes,''),status=coalesce(supplied_status,'to_research'),
        deleted_at=null,version=version+1,updated_at=moment
        where owner_id=caller and id=current_row.id returning * into current_row;
    else
      if (identity_hash is not null and identity_hash <> current_row.url_key)
          or (p_payload ? 'source_id' and supplied_source is distinct from current_row.source_id)
          or (p_payload ? 'source_issue_date' and supplied_issue is distinct from current_row.source_issue_date) then
        raise exception using errcode='22023',message='record_identity_immutable';
      end if;
      update xait_private.saved_projects set title=coalesce(supplied_title,title),
        notes=coalesce(supplied_notes,notes),status=coalesce(supplied_status,status),
        version=version+1,updated_at=moment
        where owner_id=caller and id=current_row.id returning * into current_row;
    end if;
    result_kind := 'applied';
  end if;

  insert into xait_private.record_mutation_receipts (
    owner_id,mutation_id,request_digest,result_record_id,result_version,result_status)
    values (caller,p_mutation_id,request_hash,current_row.id,current_row.version,result_kind);
  return pg_catalog.jsonb_build_object('status',result_kind,
    'applied_version',current_row.version,
    'record',case when current_row.id is null then null else xait_private.record_json(current_row) end);
end;
$$;

alter function xait_private.url_component_decode(text) owner to postgres;
alter function xait_private.url_has_credentials(text) owner to postgres;
alter function xait_private.canonical_project_url(text) owner to postgres;
alter function xait_private.record_json(xait_private.saved_projects) owner to postgres;
alter function public.list_my_records(uuid,uuid,integer) owner to postgres;
alter function public.apply_record_mutation(uuid,uuid,uuid,text,bigint,jsonb) owner to postgres;
revoke all on all functions in schema xait_private from public, anon, authenticated;
revoke all on function public.list_my_records(uuid,uuid,integer) from public, anon, authenticated;
revoke all on function public.apply_record_mutation(uuid,uuid,uuid,text,bigint,jsonb) from public, anon, authenticated;
grant execute on function public.list_my_records(uuid,uuid,integer) to authenticated;
grant execute on function public.apply_record_mutation(uuid,uuid,uuid,text,bigint,jsonb) to authenticated;
comment on function public.apply_record_mutation(uuid,uuid,uuid,text,bigint,jsonb) is
  'Private owner-scoped versioned mutation; no credentials or public briefing data collection.';

commit;
