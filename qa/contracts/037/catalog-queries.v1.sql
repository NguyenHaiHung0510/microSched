-- 037 catalog authority v1. Every result is sorted before RFC8785 JSON hashing.
-- roles
SELECT rolname, rolcanlogin, rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls
FROM pg_catalog.pg_roles
WHERE rolname IN ('microsched_app', 'microsched_migrator')
ORDER BY rolname;

-- tables and sequences
SELECT n.nspname AS schema_name, c.relkind, c.relname, r.rolname AS owner
FROM pg_catalog.pg_class AS c
JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
JOIN pg_catalog.pg_roles AS r ON r.oid = c.relowner
WHERE n.nspname = 'microsched' AND c.relkind IN ('r', 'p', 'S')
ORDER BY c.relkind, c.relname;

-- columns
SELECT n.nspname AS schema_name, c.relname AS table_name, a.attnum, a.attname,
       pg_catalog.format_type(a.atttypid, a.atttypmod) AS data_type,
       a.attnotnull, pg_catalog.pg_get_expr(d.adbin, d.adrelid, true) AS default_expr
FROM pg_catalog.pg_attribute AS a
JOIN pg_catalog.pg_class AS c ON c.oid = a.attrelid
JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
LEFT JOIN pg_catalog.pg_attrdef AS d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
WHERE n.nspname = 'microsched' AND c.relkind IN ('r', 'p')
  AND a.attnum > 0 AND NOT a.attisdropped
ORDER BY c.relname, a.attnum;

-- constraints
SELECT n.nspname AS schema_name, c.relname AS table_name, x.conname, x.contype,
       x.convalidated, pg_catalog.pg_get_constraintdef(x.oid, true) AS definition
FROM pg_catalog.pg_constraint AS x
JOIN pg_catalog.pg_class AS c ON c.oid = x.conrelid
JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
WHERE n.nspname = 'microsched'
ORDER BY c.relname, x.conname;

-- all indexes, including PK/UNIQUE constraint backing indexes
SELECT schemaname, tablename, indexname, indexdef
FROM pg_catalog.pg_indexes
WHERE schemaname = 'microsched'
ORDER BY tablename, indexname;

-- non-internal triggers
SELECT n.nspname AS schema_name, c.relname AS table_name, t.tgname,
       pn.nspname AS function_schema, p.proname AS function_name, t.tgenabled,
       pg_catalog.pg_get_triggerdef(t.oid, true) AS definition
FROM pg_catalog.pg_trigger AS t
JOIN pg_catalog.pg_class AS c ON c.oid = t.tgrelid
JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
JOIN pg_catalog.pg_proc AS p ON p.oid = t.tgfoid
JOIN pg_catalog.pg_namespace AS pn ON pn.oid = p.pronamespace
WHERE n.nspname = 'microsched' AND NOT t.tgisinternal
ORDER BY c.relname, t.tgname;

-- schema ACL expanded from pg_namespace.nspacl; compare the complete grantee set
SELECT n.nspname AS schema_name,
       COALESCE(grantee.rolname, 'PUBLIC') AS grantee,
       x.privilege_type, x.is_grantable
FROM pg_catalog.pg_namespace AS n
CROSS JOIN LATERAL pg_catalog.aclexplode(
  COALESCE(n.nspacl, pg_catalog.acldefault('n', n.nspowner))
) AS x
LEFT JOIN pg_catalog.pg_roles AS grantee ON grantee.oid = x.grantee
WHERE n.nspname = 'microsched'
ORDER BY grantee, x.privilege_type;

-- explicit table and sequence grants, including every role and PUBLIC oid 0
SELECT n.nspname AS schema_name, c.relkind, c.relname,
       COALESCE(grantee.rolname, 'PUBLIC') AS grantee,
       x.privilege_type, x.is_grantable
FROM pg_catalog.pg_class AS c
JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
CROSS JOIN LATERAL pg_catalog.aclexplode(
  COALESCE(c.relacl, pg_catalog.acldefault(CASE WHEN c.relkind = 'S' THEN 'S'::"char" ELSE 'r'::"char" END, c.relowner))
) AS x
LEFT JOIN pg_catalog.pg_roles AS grantee ON grantee.oid = x.grantee
WHERE n.nspname = 'microsched' AND c.relkind IN ('r', 'p', 'S')
ORDER BY c.relkind, c.relname, grantee, x.privilege_type;

-- raw bootstrap pg_default_acl rows are summarized BEFORE aclexplode so empty ACL arrays remain visible
SELECT COUNT(*) AS raw_row_count,
       COALESCE(
         jsonb_agg(
           jsonb_build_object(
             'owner', raw.owner_name,
             'schema_name', raw.schema_name,
             'object_kind', raw.object_kind,
             'acl_item_count', raw.acl_item_count,
             'acl_text', raw.acl_text
           ) ORDER BY raw.owner_name, raw.schema_name, raw.object_kind, raw.acl_text
         ),
         '[]'::jsonb
       ) AS raw_tuples
FROM (
  SELECT owner.rolname AS owner_name,
         COALESCE(n.nspname, 'GLOBAL') AS schema_name,
         d.defaclobjtype AS object_kind,
         COALESCE(cardinality(d.defaclacl), 0) AS acl_item_count,
         COALESCE(d.defaclacl::text, '{}') AS acl_text
  FROM pg_catalog.pg_default_acl AS d
  JOIN pg_catalog.pg_roles AS owner ON owner.oid = d.defaclrole
  LEFT JOIN pg_catalog.pg_namespace AS n ON n.oid = d.defaclnamespace
  WHERE owner.rolname = 'postgres'
) AS raw;

-- effective default ACLs for all relevant owners, including the no-row acldefault case
WITH target_default_acl AS (
  SELECT owner.oid AS owner_oid, owner.rolname AS owner_name,
         n.oid AS schema_oid, n.nspname AS schema_name, object_type.objtype
  FROM pg_catalog.pg_roles AS owner
  CROSS JOIN pg_catalog.pg_namespace AS n
  CROSS JOIN (VALUES ('r'::"char"), ('S'::"char")) AS object_type(objtype)
  WHERE owner.rolname IN ('microsched_migrator', 'microsched_app', 'postgres')
    AND n.nspname = 'microsched'
)
SELECT target.owner_name AS owner, target.schema_name, target.objtype AS defaclobjtype,
       COALESCE(grantee.rolname, 'PUBLIC') AS grantee,
       x.privilege_type, x.is_grantable
FROM target_default_acl AS target
LEFT JOIN pg_catalog.pg_default_acl AS d
  ON d.defaclrole = target.owner_oid
 AND d.defaclnamespace = target.schema_oid
 AND d.defaclobjtype = target.objtype
CROSS JOIN LATERAL pg_catalog.aclexplode(
  COALESCE(d.defaclacl, pg_catalog.acldefault(target.objtype, target.owner_oid))
) AS x
LEFT JOIN pg_catalog.pg_roles AS grantee ON grantee.oid = x.grantee
ORDER BY target.owner_name, target.objtype, grantee, x.privilege_type;

-- separate expanded bootstrap privileges; raw summary above catches rows whose ACL array is empty
SELECT owner.rolname AS owner, COALESCE(n.nspname, 'GLOBAL') AS schema_name,
       d.defaclobjtype, COALESCE(grantee.rolname, 'PUBLIC') AS grantee,
       x.privilege_type, x.is_grantable
FROM pg_catalog.pg_default_acl AS d
JOIN pg_catalog.pg_roles AS owner ON owner.oid = d.defaclrole
LEFT JOIN pg_catalog.pg_namespace AS n ON n.oid = d.defaclnamespace
CROSS JOIN LATERAL pg_catalog.aclexplode(d.defaclacl) AS x
LEFT JOIN pg_catalog.pg_roles AS grantee ON grantee.oid = x.grantee
WHERE owner.rolname = 'postgres'
ORDER BY schema_name, d.defaclobjtype, grantee, x.privilege_type;

-- any ACL reference to the bootstrap role is a residual grant and must exact-set compare to []
SELECT acl_source, schema_name, object_name, grantee, privilege_type, is_grantable
FROM (
  SELECT 'schema'::text AS acl_source, n.nspname AS schema_name, NULL::text AS object_name,
         grantee.rolname AS grantee, x.privilege_type, x.is_grantable
  FROM pg_catalog.pg_namespace AS n
  CROSS JOIN LATERAL pg_catalog.aclexplode(COALESCE(n.nspacl, pg_catalog.acldefault('n', n.nspowner))) AS x
  JOIN pg_catalog.pg_roles AS grantee ON grantee.oid = x.grantee
  WHERE n.nspname = 'microsched'
  UNION ALL
  SELECT 'object', n.nspname, c.relname, grantee.rolname, x.privilege_type, x.is_grantable
  FROM pg_catalog.pg_class AS c
  JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
  CROSS JOIN LATERAL pg_catalog.aclexplode(
    COALESCE(c.relacl, pg_catalog.acldefault(CASE WHEN c.relkind = 'S' THEN 'S'::"char" ELSE 'r'::"char" END, c.relowner))
  ) AS x
  JOIN pg_catalog.pg_roles AS grantee ON grantee.oid = x.grantee
  WHERE n.nspname = 'microsched' AND c.relkind IN ('r', 'p', 'S')
) AS all_acl
WHERE grantee = 'postgres'
ORDER BY acl_source, schema_name, object_name, privilege_type;

-- revision
SELECT version_num FROM microsched.alembic_version ORDER BY version_num;
