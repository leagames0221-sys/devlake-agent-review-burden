# GitHub の PR の担当者を DevLake に取り込む

DevLake v1.0.3-beta18 の GitHub の取り込みは、PR の担当者(assignee)を `pull_request_assignees` に書きません(根拠と原文は
[ADR 0003](adr/0003-github-pr-assignee-importer.md))。そのため `sql/mysql/agent_review_burden.sql` の「担当者を除いた反応時間」は、
GitHub のデータでは「反応時間」と同じ値になります。この script は、GitHub から担当者を読み、DevLake の表に足す `.sql` を書き出します。

- script は GitHub を読むだけで、DB には接続しません。DB に流すのは、あなたが打つ 1 行です(手順 3)。
- 使うのは Python の標準ライブラリだけです。費用は 0 円です。
- script が書く行は、`_raw_data_table` が `_raw_github_ext_pull_request_assignees` の行だけです。DevLake が書いた行には触りません。

## 用意するもの

- Python 3(標準ライブラリだけで動きます)。
- DevLake を `docker compose` で動かしていること。DevLake v1.0.3-beta18 の `docker-compose-dev-mysql.yml` の原文では、
  サービス名は `mysql`(L21)、DB 名は `lake`(L30)、利用者名は `merico`(L31)、パスワードの変数は `MYSQL_PASSWORD`(L32)です
  (保存した原文の行番号。保存元は ADR 0003 の表)。配布用の別の compose を使っている場合は、この 4 つを読み替えてください。
- DevLake の GitHub の接続の番号(`--connection-id` に使う数字)。DevLake にすでに GitHub の PR が入っているなら、次で分かります。
  ```
  echo "SELECT DISTINCT SUBSTRING_INDEX(SUBSTRING_INDEX(id, ':', 3), ':', -1) AS connection_id FROM pull_requests WHERE id LIKE 'github:GithubPullRequest:%'" | docker compose exec -T mysql sh -c 'mysql -umerico -p"$MYSQL_PASSWORD" lake'
  ```
  (PR の id は `github:GithubPullRequest:<接続の番号>:<id>` の形です。)

## 手順(Git Bash で打ちます)

1. この repo を置いたフォルダへ `cd` で移ります(`devlake-agent-review-burden` という名前のフォルダです)。
   ```
   cd この repo を置いたフォルダ
   ```
2. `.sql` を作ります。`OWNER/NAME` は取り込んだ GitHub の repo、`1` は上で調べた接続の番号です。
   ```
   python importer/github_pr_assignees.py --repo OWNER/NAME --connection-id 1 --out out.sql
   ```
   - 公開 repo は、トークン無しでも読めます(1 時間に 60 回まで。1 回で PR を 100 件読みます)。
   - 回数が足りない時、または非公開 repo の時は、GitHub の画面であなたが作ったトークンを、**この端末の中だけ**に設定します。
     次の 1 行を打つと入力待ちになるので、トークンを貼って Enter を押します(貼った文字は画面に出ず、コマンドの履歴にも残りません。
     トークンは `.sql` にも出ません)。端末を閉じると消えます。手順 2 の `python` は、同じ端末で打ちます。
     ```
     read -rsp 'GitHub のトークン: ' GITHUB_TOKEN && echo && export GITHUB_TOKEN
     ```
   - HTTP 403 や 429 が返ったら、script は止まり、`.sql` を書きません。何頁まで読んだかが表示されます。繰り返し打たずに、しばらく待つか、トークンを使ってください。
   - HTTP 301 や 308 が表示されたら、その repo は名前が変わったか、移っています。新しい名前で `--repo` を指定し直してください。
   - 止まった時(終了コード 1 か 2)は、`--out` に前回の `.sql` が残っていても、script がそれを消します。前回の `.sql` を間違って流すことはありません。
   - GitHub の答えが `https://api.github.com/` 以外の場所から来た時も、読んだ中身を使わずに止まります。
3. DevLake の `docker-compose` のあるフォルダで、`.sql` を流します(`out.sql` は手順 2 で作ったファイルのパスにします)。
   ```
   docker compose exec -T mysql sh -c 'mysql -umerico -p"$MYSQL_PASSWORD" lake' < out.sql
   ```
   - 「Using a password on the command line」という警告が出ても、失敗ではありません。
   - 流した後に、次の 1 行の表が表示されます。`rows_in_table` が入った行の数、`prs_not_in_devlake` が「DevLake にまだ無くて、行を作らなかった PR」の数です。
     `rows_expected_if_all_prs_in_devlake` は、その PR にも行ができた場合の数です。`prs_skipped_invalid` は、値が規則に合わず飛ばした PR の数です。
     ```
     repo  pages_read  page_urls  prs_read  prs_skipped_invalid  rows_expected_if_all_prs_in_devlake  rows_in_table  prs_not_in_devlake
     ```
   - 全体が 1 つの取引(`START TRANSACTION;` から `COMMIT;`)なので、途中で失敗した時は何も変わりません。

### PowerShell で打つ場合(Git Bash が使えない時だけ)

この手順は Git Bash で打つ形が正です。PowerShell では `<` が使えません(`out.sql` を `<` で渡す手順 3 の形は、Git Bash でだけ動きます)。
PowerShell 5.1 は、外部コマンドに渡す引数の `"` を落とします。次の形は、**DB のパスワードに空白や記号が無い時だけ**動きます。

```
Get-Content -Raw out.sql | docker compose exec -T mysql sh -c 'mysql -umerico -p"$MYSQL_PASSWORD" lake'
```

パスワードに空白や記号がある時は、Git Bash で打ってください。

## 何度流しても同じ

- 同じ `.sql` を何度流しても、行の数は変わりません(流すたびに、読んだ PR の分だけ、当方の行を消して入れ直します)。
- PR から担当者が外れていたら、次に流した時にその行が消えます。担当者が 0 人になった PR は 0 行になります。
- 次回の入力に無かった PR の行は、そのまま残ります(消すのは、その回に読んだ PR の分だけです)。
- DevLake の「全件の取り込み直し」では、当方の行は消えません。DevLake の「scope(repo)を消す」操作では、当方の行も一緒に消えます。
  この 2 点は、試験の DB では確かめています(`tests/importer/test_importer.py` の A9・A10)。実際の DevLake での確認は ADR 0003 の「U4 で確かめる事」にあります。

## 試験

Docker Desktop を起動して、次を打ちます(通信はしません。MySQL の container を起こして、終わったら消します)。

```
python tests/importer/test_importer.py
python tests/importer/test_importer.py --mutants
```
