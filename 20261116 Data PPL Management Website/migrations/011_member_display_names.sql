SET @display_name_sql = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='members' AND column_name='display_name'),
  'SELECT 1',
  'ALTER TABLE members ADD COLUMN display_name VARCHAR(80) NOT NULL DEFAULT '''''
);
PREPARE display_name_ddl FROM @display_name_sql;
EXECUTE display_name_ddl;
DEALLOCATE PREPARE display_name_ddl;
