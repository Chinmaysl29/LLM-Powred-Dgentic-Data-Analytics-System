-- READ ONLY: run in the hosted project's SQL Editor, not the local database.
-- Returns policy/grant definitions and bucket configuration, never customer rows.
BEGIN READ ONLY;
SET LOCAL statement_timeout = '10s';
SELECT n.nspname AS schema, c.relname AS table_name,
       c.relrowsecurity AS rls_enabled, c.relforcerowsecurity AS rls_forced
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname IN ('public', 'storage') AND c.relkind IN ('r','p')
ORDER BY 1,2;
SELECT schemaname, tablename, policyname, permissive, roles, cmd, qual, with_check
FROM pg_policies WHERE schemaname IN ('public','storage') ORDER BY 1,2,3;
SELECT table_schema, table_name, grantee, privilege_type
FROM information_schema.role_table_grants
WHERE table_schema IN ('public','storage')
  AND grantee IN ('anon','authenticated','service_role','PUBLIC') ORDER BY 1,2,3,4;
SELECT n.nspname AS schema, p.proname AS function, p.prosecdef AS security_definer,
       p.proconfig AS function_settings
FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
WHERE n.nspname='public' ORDER BY 1,2;
SELECT id, public, file_size_limit, allowed_mime_types FROM storage.buckets ORDER BY id;
SELECT conrelid::regclass::text AS table_name, conname, pg_get_constraintdef(oid) AS definition
FROM pg_constraint WHERE contype IN ('f','u','p')
  AND connamespace='public'::regnamespace ORDER BY 1,2;
ROLLBACK;
