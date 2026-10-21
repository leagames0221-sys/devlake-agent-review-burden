-- Test-only: columns that tests/schema_mysql.sql (U1) does not have and that the importer (U3) needs.
-- tests/schema_mysql.sql is not changed; this file is loaded after it (tests/importer/test_importer.py).
-- Types follow the gorm tags of Apache DevLake tag v1.0.3-beta18 (Apache-2.0):
--   [BASE] https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/core/models/common/base.go
--          (the line numbers below are those of the original file at that URL; a copy that is saved with a header line has them one more)
--   RawDataOrigin (embedded in NoPKModel, which DomainEntity and PullRequestAssignee embed):
--     [BASE] RawDataParams  string  gorm:"column:_raw_data_params;type:varchar(255);index"   (original line 54)
--     [BASE] RawDataTable   string  gorm:"column:_raw_data_table;type:varchar(255)"          (original line 55)
--     [BASE] RawDataId      uint64  gorm:"column:_raw_data_id"                                (original line 57)
--     [BASE] RawDataRemark  string  gorm:"column:_raw_data_remark"                            (original line 59)
--   NoPKModel: CreatedAt, UpdatedAt  time.Time                                               (original lines 71-72)
-- Where gorm gives no explicit type (uint64 / string / time.Time) the MySQL type below is the usual gorm
-- default (bigint unsigned / longtext / datetime(3)); that mapping is an approximation, as in schema_mysql.sql.
-- Whether the real table allows NULL in these columns is one of the things U4 checks (ADR 0003).

ALTER TABLE pull_requests
  ADD COLUMN _raw_data_params VARCHAR(255),
  ADD COLUMN _raw_data_table  VARCHAR(255),
  ADD INDEX idx_pull_requests__raw_data_params (_raw_data_params);

ALTER TABLE pull_request_assignees
  ADD COLUMN _raw_data_params VARCHAR(255),
  ADD COLUMN _raw_data_table  VARCHAR(255),
  ADD COLUMN _raw_data_id     BIGINT UNSIGNED,
  ADD COLUMN _raw_data_remark LONGTEXT,
  ADD COLUMN created_at       DATETIME(3),
  ADD COLUMN updated_at       DATETIME(3),
  ADD INDEX idx_pull_request_assignees__raw_data_params (_raw_data_params);
