"""Offline SQL-contract checks, not a substitute for executing the SQL suite.

The live isolation suite is supabase/tests/private_project_library.sql.  This
stdlib test never connects to a database or reads configuration/credentials.
"""

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "supabase/migrations/202610270001_private_project_library.sql"
LIVE_TEST = ROOT / "supabase/tests/private_project_library.sql"
SETUP = ROOT / "docs-source/records-setup.md"


class RecordsBackendContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sql = MIGRATION.read_text(encoding="utf-8")
        cls.lower = cls.sql.lower()
        cls.live = LIVE_TEST.read_text(encoding="utf-8")

    def test_migration_is_transactional_and_has_no_destructive_replacement(self):
        self.assertRegex(self.lower, r"(?m)^begin;$")
        self.assertRegex(self.lower, r"(?m)^commit;$")
        self.assertNotRegex(self.lower, r"\bdrop\s+(?:table|schema)\b")
        self.assertNotIn("create or replace", self.lower)
        self.assertEqual(self.sql.count("$$") % 2, 0)

    def test_private_tables_have_rls_and_no_anonymous_grants(self):
        for name in ("saved_projects", "record_mutation_receipts"):
            self.assertIn("alter table xait_private." + name + " enable row level security", self.lower)
            self.assertIn("alter table xait_private." + name + " force row level security", self.lower)
            self.assertIn("revoke all on xait_private." + name + " from public, anon, authenticated", self.lower)
        self.assertIn("using ((select auth.uid()) = owner_id)", self.lower)
        self.assertIn("for all to postgres using ((select auth.uid()) = owner_id)", self.lower)
        self.assertIn("with check ((select auth.uid()) = owner_id)", self.lower)
        self.assertNotRegex(self.lower, r"grant\s+(?:all|insert|update|delete)\s+on\s+xait_private")

    def test_exact_rpc_contract_and_privileges(self):
        self.assertIn("public.list_my_records(p_account_id uuid, p_after_id uuid default null, p_limit integer default 100)", self.sql)
        self.assertIn("p_account_id uuid, p_mutation_id uuid, p_record_id uuid, p_operation text", self.sql)
        self.assertIn("p_expected_version bigint, p_payload jsonb", self.sql)
        self.assertIn("'records', rows_json", self.sql)
        self.assertIn("'next_after'", self.sql)
        self.assertIn("grant execute on function public.list_my_records(uuid,uuid,integer) to authenticated", self.lower)
        self.assertIn("grant execute on function public.apply_record_mutation(uuid,uuid,uuid,text,bigint,jsonb) to authenticated", self.lower)
        self.assertNotRegex(self.lower, r"grant execute[^;]+to\s+(?:public|anon)\b")

    def test_definer_functions_explicitly_check_identity_and_lock_owner(self):
        bodies = re.findall(r"create function public\.[\s\S]+?\n\$\$;", self.sql)
        self.assertEqual(len(bodies), 2)
        for body in bodies:
            self.assertIn("security definer set search_path = ''", body)
            self.assertIn("caller uuid := auth.uid()", body)
            self.assertIn("if caller is null then", body)
            self.assertIn("authentication_required", body)
            self.assertIn("if p_account_id is distinct from caller then", body)
            self.assertIn("account_changed", body)
            self.assertIn("owner_id = caller", body)
        self.assertIn("pg_advisory_xact_lock", self.sql)
        self.assertNotRegex(self.lower, r"\bexecute\s+['\"]")

    def test_payload_ownership_and_unknown_fields_are_rejected(self):
        self.assertIn("key_name not in ('url','title','source_id','source_issue_date','notes','status','canonical_url')", self.sql)
        self.assertIn("message = 'invalid_payload'", self.sql)
        self.assertIn("message = 'invalid_canonical_url'", self.sql)
        self.assertNotIn("p_payload ->> 'owner_id'", self.sql)
        self.assertNotIn("p_payload ->> 'version'", self.sql)

    def test_duplicates_versions_and_historical_replay_have_server_guards(self):
        self.assertIn("unique (owner_id, url_key)", self.lower)
        self.assertIn("primary key (owner_id, mutation_id)", self.lower)
        self.assertIn("receipt.request_digest <> request_hash", self.sql)
        self.assertIn("'applied_version',receipt.result_version", self.sql)
        self.assertIn("'applied_version',current_row.version", self.sql)
        self.assertIn("message = 'mutation_id_reused'", self.sql)
        self.assertIn("p_expected_version <> current_row.version", self.sql)
        self.assertIn("then 'existing' else 'deleted'", self.sql)
        self.assertIn("version=version+1", self.sql)
        receipt_table = self.sql.split("create table xait_private.record_mutation_receipts (", 1)[1].split("\n);", 1)[0]
        for prohibited in ("notes", "payload", "token", "session"):
            self.assertNotIn(prohibited, receipt_table)

    def test_delete_is_a_versioned_content_free_tombstone(self):
        self.assertIn("canonical_url=null,url=null,title=null", self.sql)
        self.assertIn("source_id=null,source_issue_date=null,notes=null,status='to_research',deleted_at=moment", self.sql)
        self.assertIn("and notes is null and status = 'to_research'", self.sql)
        record_json = self.sql.split("create function xait_private.record_json", 1)[1].split("\n$$;", 1)[0]
        self.assertIn("case when (p_record).deleted_at is null then (p_record).status", record_json)
        self.assertIn("else 'to_research' end", record_json)
        self.assertIn("p_operation = 'restore' and current_row.deleted_at is null", self.sql)
        self.assertIn("identity_hash <> current_row.url_key", self.sql)
        self.assertNotRegex(self.lower, r"delete from\s+xait_private\.saved_projects")

    def test_limits_are_server_side_and_unicode_aware(self):
        self.assertEqual(self.sql.count("active_count >= 1000"), 2)
        self.assertIn("char_length(supplied_notes) > 5000", self.sql)
        self.assertIn("char_length(supplied_title) not between 1 and 200", self.sql)
        self.assertIn("char_length(p_url) not between 1 and 2048", self.sql)
        self.assertIn("'record_limit_reached'", self.sql)

    def test_permanent_receipts_and_tombstones_have_transactional_budgets(self):
        self.assertIn("receipt_count >= 10000", self.sql)
        self.assertIn("identity_count >= 5000", self.sql)
        self.assertEqual(self.sql.count("message = 'storage_limit_reached'"), 2)
        self.assertLess(self.sql.index("if found then\n    if receipt.request_digest"),
                        self.sql.index("receipt_count >= 10000"))
        self.assertLess(self.sql.index("pg_advisory_xact_lock"),
                        self.sql.index("receipt_count >= 10000"))
        self.assertNotRegex(self.lower, r"delete from\s+xait_private\.record_mutation_receipts")
        self.assertNotRegex(self.lower, r"\btruncate\b")

    def test_unknown_records_cannot_allocate_receipts(self):
        guard = self.sql.split("if p_operation <> 'create' and current_row.id is null then", 1)[1].split("\n  end if;", 1)[0]
        self.assertIn("return pg_catalog.jsonb_build_object('status','deleted'", guard)
        self.assertIn("'applied_version',null,'record',null", guard)
        self.assertNotIn("insert into", guard)
        self.assertLess(self.sql.index("if p_operation <> 'create' and current_row.id is null then"),
                        self.sql.index("receipt_count >= 10000"))

    def test_link_validation_does_not_fetch_or_rewrite_semantic_identity(self):
        for value in ("utm_source", "fbclid", "gclid", "mc_eid"):
            self.assertIn("'" + value + "'", self.sql)
        self.assertIn("query_piece", self.sql)
        self.assertIn("fragment_text", self.sql)
        self.assertIn("'localhost'", self.sql)
        self.assertIn("'invalid_url'", self.sql)
        self.assertIn("localtest\\.me|lvh\\.me|nip\\.io|sslip\\.io|xip\\.io", self.sql)
        self.assertIn("if fragment_text is not null then", self.sql)
        self.assertIn("auth|credential|token|secret|password|cookie|session|signature", self.sql)
        self.assertIn("for pass in 1..3 loop", self.sql)
        self.assertIn("url_has_credentials(coalesce(fragment_text,''))", self.sql)
        self.assertNotIn("http_get(", self.lower)
        self.assertNotIn("net.http", self.lower)

    def test_wire_record_contains_no_owner_or_authentication_data(self):
        output = self.sql.split("create function xait_private.record_json", 1)[1].split("\n$$;", 1)[0]
        for name in ("id", "url_key", "canonical_url", "source_issue_date", "notes", "version", "deleted_at"):
            self.assertIn("'" + name + "'", output)
        for name in ("owner_id", "access_token", "refresh_token", "session"):
            self.assertNotIn("'" + name + "'", output)

    def test_live_suite_rolls_back_and_covers_isolation_and_queue_safety(self):
        self.assertRegex(self.live, r"(?m)^begin;$")
        self.assertRegex(self.live, r"(?m)^rollback;$")
        self.assertNotRegex(self.live, r"(?mi)^commit;$")
        for marker in ("set local role anon", "reader_b_cannot_list_a", "reader_b_cannot_update_a",
                       "rls_direct_read_is_owner_scoped", "idempotent_create_replay",
                       "duplicate_does_not_reset_notes", "stale_version_conflicts",
                       "offline_update_does_not_resurrect", "create_cannot_restore_tombstone",
                       "explicit_restore", "quota_after_delete", "pagination_next_page",
                       "expected_account_read_rejected", "expected_account_write_rejected",
                       "delete_clears_followup_status_in_response", "delete_clears_followup_status_in_storage",
                       "tombstone_list_has_only_neutral_status", "missing_record_mutations_do_not_grow_receipts",
                       "total_identity_budget_does_not_grow", "receipt_budget_preserves_old_replay",
                       "receipt_budget_does_not_grow_or_prune", "receipt_budget_does_not_apply_refused_write"):
            self.assertIn(marker, self.live)

    def test_setup_documents_required_manual_gates(self):
        text = SETUP.read_text(encoding="utf-8")
        for marker in ("Free", "PKCE", "RLS", "publishable", "GitHub", "关闭", "手机", "隔离测试"):
            self.assertIn(marker, text)
        self.assertIn("不读取", text)
        self.assertIn("private_project_library.sql", text)
        self.assertIn("10,000", text)
        self.assertIn("storage_limit_reached", text)
        self.assertIn("不自动清理回执", text)


if __name__ == "__main__":
    unittest.main()
