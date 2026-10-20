-- Test-only DDL for the DevLake domain-layer tables that the metric SQL reads.
-- Column names follow gorm's default snake_case naming of the Go struct fields.
-- Types follow the gorm tags of Apache DevLake tag v1.0.3-beta18 (Apache-2.0).
-- Only the columns the metric SQL uses are created.
--
-- Source files (copies with line numbers kept under the research folder, first
-- line of each = path + ref + retrieval date):
--   [PR]   backend/core/models/domainlayer/code/pull_request.go
--   [CMT]  backend/core/models/domainlayer/code/pull_request_comment.go
--   [ASG]  backend/core/models/domainlayer/code/pull_request_assignees.go
--   [ACC]  backend/core/models/domainlayer/crossdomain/account.go
--   [DE]   backend/core/models/domainlayer/domainlayer.go   (DomainEntity.Id)
-- Where gorm gives no explicit type (plain string / time.Time / int / bool) the
-- MySQL type below is the usual gorm default (longtext / datetime(3) / bigint /
-- tinyint(1)); that mapping is an approximation, marked "default".

CREATE TABLE accounts (
  id        VARCHAR(255) NOT NULL,  -- [DE] L26 Id gorm:"primaryKey;type:varchar(255)"
  user_name VARCHAR(255),           -- [ACC] L31 UserName gorm:"type:varchar(255)"
  is_bot    TINYINT(1) DEFAULT 0,   -- [ACC] L36 IsBot bool gorm:"default:false"
  PRIMARY KEY (id)
);

CREATE TABLE pull_requests (
  id           VARCHAR(255) NOT NULL, -- [DE] L26 Id gorm:"primaryKey;type:varchar(255)"
  base_repo_id VARCHAR(255),          -- [PR] L37 BaseRepoId gorm:"index" (no explicit type; varchar(255) approximates)
  status       VARCHAR(100),          -- [PR] L39 Status gorm:"type:varchar(100)"; values OPEN/CLOSED/MERGED L30-L32
  description  LONGTEXT,              -- [PR] L42 Description string (default)
  author_name  VARCHAR(100),          -- [PR] L44 AuthorName gorm:"type:varchar(100)"
  author_id    VARCHAR(100),          -- [PR] L46 AuthorId gorm:"type:varchar(100)"
  created_date DATETIME(3),           -- [PR] L51 CreatedDate time.Time (default)
  merged_date  DATETIME(3) NULL,      -- [PR] L52 MergedDate *time.Time (default)
  closed_date  DATETIME(3) NULL,      -- [PR] L53 ClosedDate *time.Time (default)
  head_ref     VARCHAR(255),          -- [PR] L57 HeadRef gorm:"type:varchar(255)"
  additions    BIGINT,                -- [PR] L61 Additions int (default)
  deletions    BIGINT,                -- [PR] L62 Deletions int (default)
  is_draft     TINYINT(1),            -- [PR] L63 IsDraft bool (default)
  PRIMARY KEY (id)
);

CREATE TABLE pull_request_comments (
  id              VARCHAR(255) NOT NULL, -- [DE] L26 Id gorm:"primaryKey;type:varchar(255)"
  pull_request_id VARCHAR(255),          -- [CMT] L29 PullRequestId gorm:"index;varchar(255)"
  body            LONGTEXT,              -- [CMT] L30 Body string (default)
  account_id      VARCHAR(255),          -- [CMT] L31 AccountId gorm:"type:varchar(255)"
  created_date    DATETIME(3) NULL,      -- [CMT] L32 CreatedDate time.Time (default). Unsent (PENDING) reviews have no
                                         --   time: src_github_pr_review_convertor.go L95-L97 only sets it when
                                         --   GithubSubmitAt != nil. NULL is used here; a live MySQL may hold a zero date.
  type            VARCHAR(255),          -- [CMT] L34 Type gorm:"type:varchar(255)"; NORMAL/DIFF/REVIEW L44-L46
  review_id       VARCHAR(255),          -- [CMT] L35 ReviewId gorm:"type:varchar(255)"
  status          VARCHAR(255),          -- [CMT] L36 Status gorm:"type:varchar(255)"; REVIEW rows carry the GitHub state
  PRIMARY KEY (id)
);

CREATE TABLE pull_request_assignees (
  pull_request_id VARCHAR(255) NOT NULL, -- [ASG] L26 PullRequestId gorm:"primaryKey;type:varchar(255)"
  assignee_id     VARCHAR(255) NOT NULL, -- [ASG] L27 AssigneeId gorm:"primaryKey;type:varchar(255)"
  name            VARCHAR(255),          -- [ASG] L28 Name gorm:"type:varchar(255)"
  user_name       VARCHAR(255),          -- [ASG] L29 UserName gorm:"type:varchar(255)"
  PRIMARY KEY (pull_request_id, assignee_id)
);
