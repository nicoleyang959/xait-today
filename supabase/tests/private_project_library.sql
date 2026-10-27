-- Run only in a new, non-public Supabase project after the migration.
-- All identities/content below are synthetic. Every data change is rolled back.
begin;

create function pg_temp.assert_true(value boolean, label text) returns void
language plpgsql as $$
begin
  if value is distinct from true then raise exception 'assertion_failed: %', label; end if;
end;
$$;
create function pg_temp.expect_error(statement text, expected_state text, expected_message text default null) returns void
language plpgsql as $$
begin
  begin
    execute statement;
  exception when others then
    if sqlstate = expected_state and (expected_message is null or sqlerrm = expected_message) then return; end if;
    raise;
  end;
  raise exception 'expected_rejection_did_not_happen';
end;
$$;

do $$
begin
  if exists (select 1 from auth.users where id in (
    '10000000-0000-4000-8000-000000000001'::uuid,
    '10000000-0000-4000-8000-000000000002'::uuid)) then
    raise exception 'fixture_identity_exists_use_a_fresh_test_project';
  end if;
end;
$$;
insert into auth.users(id, aud, role, email, created_at, updated_at) values
  ('10000000-0000-4000-8000-000000000001','authenticated','authenticated',
   'synthetic-reader-a@example.invalid',now(),now()),
  ('10000000-0000-4000-8000-000000000002','authenticated','authenticated',
   'synthetic-reader-b@example.invalid',now(),now());

select pg_temp.assert_true(
  xait_private.canonical_project_url('HTTPS://Example.ORG:443/Path/?utm_source=news&a=1#Keep')
    = 'https://example.org/Path/?a=1#Keep', 'conservative_canonicalization');
select pg_temp.assert_true(
  xait_private.canonical_project_url('https://example.org/P?%75tm_source=x&b=2&a=1#frag')
    = 'https://example.org/P?b=2&a=1#frag', 'encoded_tracking_only');
select pg_temp.assert_true(
  xait_private.canonical_project_url('https://example.org/a?b=2&a=1')
    <> xait_private.canonical_project_url('https://example.org/a?a=1&b=2'),
  'semantic_query_order_preserved');
select pg_temp.expect_error($q$select xait_private.canonical_project_url('javascript:alert(1)')$q$,'22023');
select pg_temp.expect_error($q$select xait_private.canonical_project_url('http://localhost/a')$q$,'22023');
select pg_temp.expect_error($q$select xait_private.canonical_project_url('http://10.0.0.1/a')$q$,'22023');
select pg_temp.expect_error($q$select xait_private.canonical_project_url('https://name@example.org/a')$q$,'22023');
select pg_temp.expect_error($q$select xait_private.canonical_project_url('https://example.org/a?%74oken=fixture')$q$,'22023');
select pg_temp.expect_error($q$select xait_private.canonical_project_url('https://example.org/a#access_token=fixture')$q$,'22023');
select pg_temp.expect_error($q$select xait_private.canonical_project_url('https://example.org/a#%74oken=fixture')$q$,'22023');
select pg_temp.expect_error($q$select xait_private.canonical_project_url('https://example.org/a#%2561pi_key%253Dfixture')$q$,'22023');
select pg_temp.expect_error($q$select xait_private.canonical_project_url('https://example.org/a#/route?token=fixture')$q$,'22023');
select pg_temp.expect_error($q$select xait_private.canonical_project_url('https://example.org/a?my_auth_value=fixture')$q$,'22023');
select pg_temp.expect_error($q$select xait_private.canonical_project_url('https://public-name.localtest.me/a')$q$,'22023');
select pg_temp.expect_error($q$select xait_private.canonical_project_url('https://public-name.nip.io/a')$q$,'22023');

set local role anon;
select pg_temp.expect_error($q$select public.list_my_records(auth.uid(),null,100)$q$,'42501');
select pg_temp.expect_error($q$select public.apply_record_mutation(auth.uid(),
  '30000000-0000-4000-8000-000000000001','20000000-0000-4000-8000-000000000001',
  'create',0,'{}')$q$,'42501');
reset role;
select set_config('request.jwt.claim.sub','',true);
set local role authenticated;
select pg_temp.expect_error($q$select public.list_my_records(auth.uid(),null,100)$q$,'28000');
reset role;

select set_config('request.jwt.claim.sub','10000000-0000-4000-8000-000000000001',true);
set local role authenticated;
select pg_temp.assert_true((public.apply_record_mutation(auth.uid(),
  '30000000-0000-4000-8000-000000000001','20000000-0000-4000-8000-000000000001',
  'create',0,'{"url":"HTTPS://Example.ORG:443/Path/?utm_source=news&a=1#Keep","title":"Synthetic project A","notes":"Synthetic note A","status":"watching"}')
  ->>'status')='applied','create_own');
select pg_temp.assert_true((public.apply_record_mutation(auth.uid(),
  '30000000-0000-4000-8000-000000000001','20000000-0000-4000-8000-000000000001',
  'create',0,'{"url":"HTTPS://Example.ORG:443/Path/?utm_source=news&a=1#Keep","title":"Synthetic project A","notes":"Synthetic note A","status":"watching"}')
  ->'record'->>'version')='1','idempotent_create_replay');
select pg_temp.expect_error($q$select public.apply_record_mutation(auth.uid(),
  '30000000-0000-4000-8000-000000000001','20000000-0000-4000-8000-000000000001',
  'create',0,'{"url":"https://example.org/different","title":"Different payload"}')$q$,'22023');
select pg_temp.assert_true((public.apply_record_mutation(auth.uid(),
  '30000000-0000-4000-8000-000000000002','20000000-0000-4000-8000-000000000009',
  'create',0,'{"url":"https://example.org/Path/?a=1#Keep","title":"Different title","notes":"Must not replace"}')
  ->'record'->>'notes')='Synthetic note A','duplicate_does_not_reset_notes');
select pg_temp.expect_error($q$select public.apply_record_mutation(auth.uid(),
  '30000000-0000-4000-8000-000000000099','20000000-0000-4000-8000-000000000099',
  'create',0,'{"url":"https://example.org/a","title":"Fixture","owner_id":"10000000-0000-4000-8000-000000000002"}')$q$,'22023');
select pg_temp.expect_error($q$update xait_private.saved_projects set version=9$q$,'42501');
select pg_temp.expect_error($q$delete from xait_private.saved_projects$q$,'42501');
select pg_temp.expect_error($q$select public.list_my_records(auth.uid(),null,101)$q$,'22023');
select pg_temp.expect_error($q$select public.apply_record_mutation(auth.uid(),
  '30000000-0000-4000-8000-000000000098','20000000-0000-4000-8000-000000000098',
  'create',0,jsonb_build_object('url','https://example.org/a','title','Fixture','notes',repeat('界',5001)))$q$,'22023');
select pg_temp.expect_error($q$select public.apply_record_mutation(auth.uid(),
  '30000000-0000-4000-8000-000000000097','20000000-0000-4000-8000-000000000097',
  'create',0,jsonb_build_object('url','https://example.org/a','title',repeat('x',201)))$q$,'22023');
select pg_temp.expect_error($q$select public.apply_record_mutation(auth.uid(),
  '30000000-0000-4000-8000-000000000096','20000000-0000-4000-8000-000000000096',
  'create',0,'{"url":"https://example.org/a","title":"Fixture","status":"public"}')$q$,'22023');
select pg_temp.assert_true((public.apply_record_mutation(auth.uid(),
  '30000000-0000-4000-8000-000000000003','20000000-0000-4000-8000-000000000001',
  'update',1,'{"notes":"Second synthetic note","status":"tried"}')
  ->'record'->>'version')='2','version_increments');
select pg_temp.assert_true((public.apply_record_mutation(auth.uid(),
  '30000000-0000-4000-8000-000000000004','20000000-0000-4000-8000-000000000001',
  'update',1,'{"notes":"Stale synthetic note"}')->>'status')='conflict','stale_version_conflicts');
select pg_temp.assert_true((public.list_my_records(auth.uid(),null,100)->'records'->0->>'notes')
  = 'Second synthetic note','conflict_keeps_cloud_note');
select pg_temp.assert_true((public.apply_record_mutation(auth.uid(),
  '30000000-0000-4000-8000-000000000001','20000000-0000-4000-8000-000000000001',
  'create',0,'{"url":"HTTPS://Example.ORG:443/Path/?utm_source=news&a=1#Keep","title":"Synthetic project A","notes":"Synthetic note A","status":"watching"}')
  ->>'applied_version')='1','lost_ack_keeps_original_applied_version');
select pg_temp.assert_true((public.apply_record_mutation(auth.uid(),
  '30000000-0000-4000-8000-000000000001','20000000-0000-4000-8000-000000000001',
  'create',0,'{"url":"HTTPS://Example.ORG:443/Path/?utm_source=news&a=1#Keep","title":"Synthetic project A","notes":"Synthetic note A","status":"watching"}')
  ->'record'->>'version')='2','lost_ack_returns_current_record_not_historical_notes');
reset role;

select set_config('request.jwt.claim.sub','10000000-0000-4000-8000-000000000002',true);
set local role authenticated;
-- Expected-account pins must reject an A outbox carrying a switched B session.
select pg_temp.expect_error($q$select public.list_my_records(
  '10000000-0000-4000-8000-000000000001',null,100)$q$,'28000');
select pg_temp.assert_true(true,'expected_account_read_rejected');
select pg_temp.expect_error($q$select public.apply_record_mutation(
  '10000000-0000-4000-8000-000000000001',
  '30000000-0000-4000-8000-000000000095','20000000-0000-4000-8000-000000000095',
  'create',0,'{"url":"https://example.org/session-race","title":"Synthetic switched account"}')$q$,'28000');
select pg_temp.assert_true(true,'expected_account_write_rejected');
select pg_temp.assert_true(jsonb_array_length(public.list_my_records(auth.uid(),null,100)->'records')=0,'reader_b_cannot_list_a');
select pg_temp.assert_true((select count(*) from xait_private.saved_projects)=0,'rls_direct_read_is_owner_scoped');
select pg_temp.assert_true((public.apply_record_mutation(auth.uid(),
  '30000000-0000-4000-8000-000000000001','20000000-0000-4000-8000-000000000001',
  'update',2,'{"notes":"Cross-account attack fixture"}')->'record')='null'::jsonb,'reader_b_cannot_update_a');
select pg_temp.assert_true((public.apply_record_mutation(auth.uid(),
  '30000000-0000-4000-8000-000000000002','20000000-0000-4000-8000-000000000003',
  'create',0,'{"url":"https://example.org/Path/?a=1#Keep","title":"Synthetic project B"}')
  ->>'status')='applied','identity_is_owner_scoped');
select pg_temp.assert_true((select count(*) from generate_series(1,256) n where
  (public.apply_record_mutation(auth.uid(),md5('missing-mutation-'||n)::uuid,
    md5('missing-record-'||n)::uuid,'delete',0,'{}')->'record')='null'::jsonb)=256,
  'missing_record_mutations_have_no_side_effect');
reset role;
select pg_temp.assert_true((select count(*) from xait_private.record_mutation_receipts
  where owner_id='10000000-0000-4000-8000-000000000002')=1,
  'missing_record_mutations_do_not_grow_receipts');

select set_config('request.jwt.claim.sub','10000000-0000-4000-8000-000000000001',true);
set local role authenticated;
select pg_temp.assert_true((public.list_my_records(auth.uid(),null,100)->'records'->0->>'notes')
  = 'Second synthetic note','reader_b_did_not_change_a');
select pg_temp.assert_true((public.apply_record_mutation(auth.uid(),
  '30000000-0000-4000-8000-000000000005','20000000-0000-4000-8000-000000000001',
  'delete',2,'{}')->'record'->>'notes') is null,'delete_clears_body');
select pg_temp.assert_true((public.apply_record_mutation(auth.uid(),
  '30000000-0000-4000-8000-000000000005','20000000-0000-4000-8000-000000000001',
  'delete',2,'{}')->'record'->>'status')='to_research','delete_clears_followup_status_in_response');
select pg_temp.assert_true((select status from xait_private.saved_projects
  where id='20000000-0000-4000-8000-000000000001')='to_research',
  'delete_clears_followup_status_in_storage');
select pg_temp.assert_true((public.list_my_records(auth.uid(),null,100)->'records'->0->>'deleted_at') is not null,'list_includes_tombstone');
select pg_temp.assert_true((public.list_my_records(auth.uid(),null,100)->'records'->0->>'status')='to_research',
  'tombstone_list_has_only_neutral_status');
select pg_temp.assert_true((public.apply_record_mutation(auth.uid(),
  '30000000-0000-4000-8000-000000000006','20000000-0000-4000-8000-000000000001',
  'update',3,'{"notes":"Old offline draft"}')->>'status')='deleted','offline_update_does_not_resurrect');
select pg_temp.assert_true((public.apply_record_mutation(auth.uid(),
  '30000000-0000-4000-8000-000000000007','20000000-0000-4000-8000-000000000009',
  'create',0,'{"url":"https://example.org/Path/?a=1#Keep","title":"Synthetic attempted recreation"}')
  ->>'status')='deleted','create_cannot_restore_tombstone');
select pg_temp.assert_true((public.apply_record_mutation(auth.uid(),
  '30000000-0000-4000-8000-000000000008','20000000-0000-4000-8000-000000000001',
  'restore',3,'{"url":"https://example.org/Path/?a=1#Keep","title":"Explicitly restored synthetic project"}')
  ->'record'->>'version')='4','explicit_restore');
select pg_temp.assert_true((public.apply_record_mutation(auth.uid(),
  '30000000-0000-4000-8000-000000000010','20000000-0000-4000-8000-000000000002',
  'create',0,'{"url":"https://example.org/second","title":"Second synthetic project"}')
  ->>'status')='applied','second_record');
select pg_temp.assert_true(public.list_my_records(auth.uid(),null,1)->>'next_after'
  = '20000000-0000-4000-8000-000000000001','pagination_cursor');
select pg_temp.assert_true(jsonb_array_length(public.list_my_records(auth.uid(),
  '20000000-0000-4000-8000-000000000001',1)->'records')=1,'pagination_next_page');
reset role;

-- Fill the remaining quota as privileged test setup, never as a browser role.
insert into xait_private.saved_projects(
  id,owner_id,url_key,canonical_url,url,title,notes)
select md5('quota-fixture-'||n)::uuid,'10000000-0000-4000-8000-000000000001',
  encode(sha256(convert_to('https://example.org/quota/'||n,'UTF8')),'hex'),
  'https://example.org/quota/'||n,'https://example.org/quota/'||n,'Synthetic quota fixture',''
from generate_series(1,998) n;
set local role authenticated;
select pg_temp.expect_error($q$select public.apply_record_mutation(auth.uid(),
  '30000000-0000-4000-8000-000000000011','20000000-0000-4000-8000-000000000011',
  'create',0,'{"url":"https://example.org/over-quota","title":"Synthetic over quota"}')$q$,'P0001');
select pg_temp.assert_true((public.apply_record_mutation(auth.uid(),
  '30000000-0000-4000-8000-000000000012','20000000-0000-4000-8000-000000000002',
  'delete',1,'{}')->>'status')='applied','delete_frees_active_quota');
select pg_temp.assert_true((public.apply_record_mutation(auth.uid(),
  '30000000-0000-4000-8000-000000000013','20000000-0000-4000-8000-000000000013',
  'create',0,'{"url":"https://example.org/replacement","title":"Synthetic replacement"}')
  ->>'status')='applied','quota_after_delete');
select pg_temp.expect_error($q$select public.apply_record_mutation(auth.uid(),
  '30000000-0000-4000-8000-000000000014','20000000-0000-4000-8000-000000000002',
  'restore',2,'{"url":"https://example.org/second","title":"Synthetic restored over quota"}')$q$,'P0001');
-- Free one active slot; total identities are a separate lifetime budget.
select public.apply_record_mutation(auth.uid(),
  '30000000-0000-4000-8000-000000000015','20000000-0000-4000-8000-000000000013',
  'delete',1,'{}');
reset role;

-- The table CHECK must reject historical follow-up markers in tombstones even
-- if privileged application code ever attempts to bypass the normal RPC.
select pg_temp.expect_error($q$update xait_private.saved_projects set status='watching'
  where owner_id='10000000-0000-4000-8000-000000000001'
  and id='20000000-0000-4000-8000-000000000013'$q$,'23514');
insert into xait_private.saved_projects(id,owner_id,url_key,deleted_at)
select md5('identity-budget-'||n)::uuid,'10000000-0000-4000-8000-000000000001',
  encode(sha256(convert_to('identity-budget-'||n,'UTF8')),'hex'),clock_timestamp()
from generate_series(1,5000-(select count(*) from xait_private.saved_projects
  where owner_id='10000000-0000-4000-8000-000000000001')) n;
set local role authenticated;
select pg_temp.expect_error($q$select public.apply_record_mutation(auth.uid(),
  '30000000-0000-4000-8000-000000000016','20000000-0000-4000-8000-000000000016',
  'create',0,'{"url":"https://example.org/identity-budget","title":"Synthetic budget refusal"}')$q$,
  'P0001','storage_limit_reached');
select pg_temp.assert_true(true,'total_identity_budget_refuses_new_identity');
select pg_temp.assert_true((public.apply_record_mutation(auth.uid(),
  '30000000-0000-4000-8000-000000000017','20000000-0000-4000-8000-000000000002',
  'restore',2,'{"url":"https://example.org/second","title":"Synthetic same identity restore"}')
  ->>'status')='applied','identity_budget_allows_explicit_existing_restore');
reset role;
select pg_temp.assert_true((select count(*) from xait_private.saved_projects
  where owner_id='10000000-0000-4000-8000-000000000001')=5000,
  'total_identity_budget_does_not_grow');

-- Populate minimal receipts directly as rolled-back fixture setup. The RPC
-- must keep old retries working without evicting any previous receipt.
insert into xait_private.record_mutation_receipts(
  owner_id,mutation_id,request_digest,result_record_id,result_version,result_status)
select '10000000-0000-4000-8000-000000000001',md5('receipt-budget-'||n)::uuid,
  encode(sha256(convert_to('receipt-budget-'||n,'UTF8')),'hex'),
  '20000000-0000-4000-8000-000000000001',4,'applied'
from generate_series(1,10000-(select count(*) from xait_private.record_mutation_receipts
  where owner_id='10000000-0000-4000-8000-000000000001')) n;
set local role authenticated;
select pg_temp.assert_true((public.apply_record_mutation(auth.uid(),
  '30000000-0000-4000-8000-000000000001','20000000-0000-4000-8000-000000000001',
  'create',0,'{"url":"HTTPS://Example.ORG:443/Path/?utm_source=news&a=1#Keep","title":"Synthetic project A","notes":"Synthetic note A","status":"watching"}')
  ->>'applied_version')='1','receipt_budget_preserves_old_replay');
select pg_temp.expect_error($q$select public.apply_record_mutation(auth.uid(),
  '30000000-0000-4000-8000-000000000018','20000000-0000-4000-8000-000000000001',
  'update',4,'{"notes":"Must remain in the local queue"}')$q$,'P0001','storage_limit_reached');
select pg_temp.assert_true(true,'receipt_budget_refuses_new_mutation');
select pg_temp.expect_error($q$select public.apply_record_mutation(auth.uid(),
  '30000000-0000-4000-8000-000000000019','20000000-0000-4000-8000-000000000001',
  'delete',4,'{}')$q$,'P0001','storage_limit_reached');
select pg_temp.assert_true((public.apply_record_mutation(auth.uid(),
  '30000000-0000-4000-8000-000000000020','20000000-0000-4000-8000-000000000020',
  'delete',0,'{}')->'record')='null'::jsonb,'missing_id_stays_free_at_receipt_budget');
reset role;
select pg_temp.assert_true((select count(*) from xait_private.record_mutation_receipts
  where owner_id='10000000-0000-4000-8000-000000000001')=10000,
  'receipt_budget_does_not_grow_or_prune');
select pg_temp.assert_true((select version from xait_private.saved_projects
  where owner_id='10000000-0000-4000-8000-000000000001'
  and id='20000000-0000-4000-8000-000000000001')=4,'receipt_budget_does_not_apply_refused_write');

select pg_temp.assert_true(not exists (
  select 1 from xait_private.record_mutation_receipts
  where owner_id='10000000-0000-4000-8000-000000000001'
  and request_digest !~ '^[0-9a-f]{64}$'),'receipts_only_store_digest');
select 'PRIVATE_LIBRARY_SQL_TESTS_PASSED' as result;
rollback;
