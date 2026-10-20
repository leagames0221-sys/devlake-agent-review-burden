-- Test-only DDL for the DevLake domain-layer tables that the metric SQL reads.
-- Column names follow gorm's default snake_case naming of the Go struct fields.
-- Types follow the gorm tags of Apache DevLake tag v1.0.3-beta18 (Apache-2.0).
-- Only the columns the metric SQL uses are created.
--
-- Source files, all at tag v1.0.3-beta18 of apache/devlake. A comment such as "[PR]#L36" means
-- the file named [PR] below, line 36; the permalink is that URL followed by "#L36".
--   [PR]   https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/core/models/domainlayer/code/pull_request.go
--   [CMT]  https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/core/models/domainlayer/code/pull_request_comment.go
--   [ASG]  https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/core/models/domainlayer/code/pull_request_assignees.go
--   [ACC]  https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/core/models/domainlayer/crossdomain/account.go
--   [DE]   https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/core/models/domainlayer/domainlayer.go   (DomainEntity.Id)
--   [PRC]  https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/core/models/domainlayer/code/pull_request_commit.go   (added for U2)
--   [COM]  https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/core/models/domainlayer/code/commit.go   (added for U2)
-- Where gorm gives no explicit type (plain string / time.Time / int / bool) the
-- MySQL type below is the usual gorm default (longtext / datetime(3) / bigint /
-- tinyint(1)); that mapping is an approximation, marked "default".

CREATE TABLE accounts (
  id        VARCHAR(255) NOT NULL,  -- [DE]#L25 Id gorm:"primaryKey;type:varchar(255)"
  user_name VARCHAR(255),           -- [ACC]#L30 UserName gorm:"type:varchar(255)"
  is_bot    TINYINT(1) DEFAULT 0,   -- [ACC]#L35 IsBot bool gorm:"default:false"
  PRIMARY KEY (id)
);

CREATE TABLE pull_requests (
  id           VARCHAR(255) NOT NULL, -- [DE]#L25 Id gorm:"primaryKey;type:varchar(255)"
  base_repo_id VARCHAR(255),          -- [PR]#L36 BaseRepoId gorm:"index" (no explicit type; varchar(255) approximates)
  status       VARCHAR(100),          -- [PR]#L38 Status gorm:"type:varchar(100)"; values OPEN/CLOSED/MERGED at [PR]#L29-L31
  description  LONGTEXT,              -- [PR]#L41 Description string (default)
  author_name  VARCHAR(100),          -- [PR]#L43 AuthorName gorm:"type:varchar(100)"
  author_id    VARCHAR(100),          -- [PR]#L45 AuthorId gorm:"type:varchar(100)"
  created_date DATETIME(3),           -- [PR]#L50 CreatedDate time.Time (default)
  merged_date  DATETIME(3) NULL,      -- [PR]#L51 MergedDate *time.Time (default)
  closed_date  DATETIME(3) NULL,      -- [PR]#L52 ClosedDate *time.Time (default)
  head_ref     VARCHAR(255),          -- [PR]#L56 HeadRef gorm:"type:varchar(255)"
  additions    BIGINT,                -- [PR]#L60 Additions int (default)
  deletions    BIGINT,                -- [PR]#L61 Deletions int (default)
  is_draft     TINYINT(1),            -- [PR]#L62 IsDraft bool (default)
  PRIMARY KEY (id)
);

CREATE TABLE pull_request_comments (
  id              VARCHAR(255) NOT NULL, -- [DE]#L25 Id gorm:"primaryKey;type:varchar(255)"
  pull_request_id VARCHAR(255),          -- [CMT]#L28 PullRequestId gorm:"index;varchar(255)"
  body            LONGTEXT,              -- [CMT]#L29 Body string (default)
  account_id      VARCHAR(255),          -- [CMT]#L30 AccountId gorm:"type:varchar(255)"
  created_date    DATETIME(3) NULL,      -- [CMT]#L31 CreatedDate time.Time (default). A review without a submit time keeps
                                         --   no time: pr_review_convertor.go#L94-L96 only sets it when GithubSubmitAt != nil
                                         --   (https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/plugins/github/tasks/pr_review_convertor.go#L94-L96).
                                         --   NULL is used here; a live MySQL may hold a zero date.
  type            VARCHAR(255),          -- [CMT]#L33 Type gorm:"type:varchar(255)"; NORMAL/DIFF/REVIEW at [CMT]#L43-L45
  review_id       VARCHAR(255),          -- [CMT]#L34 ReviewId gorm:"type:varchar(255)"
  status          VARCHAR(255),          -- [CMT]#L35 Status gorm:"type:varchar(255)"; REVIEW rows carry the GitHub state
  PRIMARY KEY (id)
);

CREATE TABLE pull_request_assignees (
  pull_request_id VARCHAR(255) NOT NULL, -- [ASG]#L25 PullRequestId gorm:"primaryKey;type:varchar(255)"
  assignee_id     VARCHAR(255) NOT NULL, -- [ASG]#L26 AssigneeId gorm:"primaryKey;type:varchar(255)"
  name            VARCHAR(255),          -- [ASG]#L27 Name gorm:"type:varchar(255)"
  user_name       VARCHAR(255),          -- [ASG]#L28 UserName gorm:"type:varchar(255)"
  PRIMARY KEY (pull_request_id, assignee_id)
);

-- U2: the two commit tables. pull_request_commits has no message column; the message is in commits and
-- is joined by sha. commits is not always filled by the default GitHub import (see docs/adr/0002).
CREATE TABLE pull_request_commits (
  commit_sha          VARCHAR(40) NOT NULL,  -- [PRC]#L27 CommitSha gorm:"primaryKey;type:varchar(40)"
  pull_request_id     VARCHAR(255) NOT NULL, -- [PRC]#L28 PullRequestId gorm:"primaryKey;type:varchar(255)"
  commit_author_name  VARCHAR(255),          -- [PRC]#L29 CommitAuthorName gorm:"type:varchar(255)"
  commit_author_email VARCHAR(255),          -- [PRC]#L30 CommitAuthorEmail gorm:"type:varchar(255)"
  commit_authored_date DATETIME(3),          -- [PRC]#L31 CommitAuthoredDate time.Time (default)
  PRIMARY KEY (commit_sha, pull_request_id)
);

CREATE TABLE commits (
  sha             VARCHAR(40) NOT NULL,  -- [COM]#L29 Sha gorm:"primaryKey;type:varchar(40)"
  message         LONGBLOB,              -- [COM]#L33 Message string has no gorm type, but a real DevLake v1.0.3-beta18 has longblob here:
                                         --   information_schema.columns, column_type = longblob, no character set (U4, docs/validation/u4-real-data.md)
  author_name     VARCHAR(255),          -- [COM]#L34 AuthorName gorm:"type:varchar(255)"
  author_email    VARCHAR(255),          -- [COM]#L35 AuthorEmail gorm:"type:varchar(255)"
  authored_date   DATETIME(3),           -- [COM]#L36 AuthoredDate time.Time (default)
  committer_name  VARCHAR(255),          -- [COM]#L38 CommitterName gorm:"type:varchar(255)"
  committer_email VARCHAR(255),          -- [COM]#L39 CommitterEmail gorm:"type:varchar(255)"
  PRIMARY KEY (sha)
);
