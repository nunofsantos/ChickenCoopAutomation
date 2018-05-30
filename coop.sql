CREATE TABLE coop_log (
  log_type    VARCHAR(255),
  log_value   VARCHAR(255),
  created     TIMESTAMP WITHOUT TIME ZONE DEFAULT (now() AT TIME ZONE 'utc')
);

CREATE INDEX IF NOT EXISTS created_index ON coop_log (
  created
);

CREATE INDEX IF NOT EXISTS log_type_index ON coop_log (
  log_type
);
