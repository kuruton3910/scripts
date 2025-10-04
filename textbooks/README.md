# Textbook Data Pipeline

教科書サジェスト機能に使うマスターデータを整形・投入するための補助スクリプト集です。

```
scripts/
└─ textbooks/
   ├─ raw/            # スクレイピングや手入力で集めた元データを置く
   │   ├─ html/       # 保存したシラバス HTML (任意)
   │   ├─ syllabus_urls.sample.csv
   │   └─ textbooks_raw.csv
   ├─ processed/      # Supabase へ投入する形式に変換した出力ファイル
   ├─ prepare_textbooks.py
   ├─ fetch_syllabus.py
   ├─ scrape_syllabus.py
   └─ README.md
```

## スクレイピングの流れ (クイックガイド)

0. GoogleClom の拡張機能を使って URL を持ってくる

1. 依存ライブラリをインストール (初回のみ)
   ```powershell
   pip install requests beautifulsoup4 python-slugify
   ```
   - 成功確認: インストール完了メッセージに `Successfully installed ...` が表示される
2. シラバス HTML を取得
   ```powershell
   python scripts/textbooks/fetch_syllabus.py --input scripts/textbooks/raw/syllabus_urls.csv --delay 1.0
   ```
   - 成功確認: コンソールに `[ok] <URL> -> scripts\textbooks\raw\html\...` が列挙され、`scripts/textbooks/raw/html/` に HTML が作成される
3. HTML から教材 CSV を抽出
   ```powershell
   python scripts/textbooks/scrape_syllabus.py --input scripts/textbooks/raw/html --output scripts/textbooks/raw/textbooks_raw.csv
   ```
   - 成功確認: 実行後に `Wrote <件数> textbook rows...` が表示され、`raw/textbooks_raw.csv` が生成されている
4. Supabase 取り込み用データを整形
   ```powershell
   python scripts/textbooks/prepare_textbooks.py
   ```
   - 成功確認: `processed/textbooks_for_import.csv`、`processed/textbooks_for_import_minimal.csv`、`processed/textbook_relations.json` が新しく生成・更新される
   - 軽量版だけ欲しい場合は `python scripts/textbooks/prepare_textbooks.py --minimal-only` で簡易 CSV のみを出力できる

### 生成された HTML の扱い

- 将来の差分比較や再抽出に使えるため、`scripts/textbooks/raw/html/` のファイルは基本的に残しておくと便利です
- 不要になったら `fetch_syllabus.py` を再実行して取り直せるので、ストレージ節約のために適宜削除・アーカイブしても構いません
- 既存ファイルと同名の HTML を再ダウンロードすると `-1`, `-2` のようにリネームされて保存されます (上書き防止)
- ファイル数が増えてきたら `manage_html.py` で状況確認・アーカイブできます

  ```powershell
  # ファイル数とサイズを確認
  python scripts/textbooks/manage_html.py stats

  # 最新 100 件だけ残し、それ以外を zip 化して削除
  python scripts/textbooks/manage_html.py archive --keep-latest 100 --delete-after

   # 学部ごとに区切りたいときは、全 HTML をひとつの zip に固めてから次の学部を処理する
   python scripts/textbooks/manage_html.py archive --keep-latest 0 --output-dir scripts/textbooks/raw/html_archive
   # zip 後に手元の html ディレクトリを空にしたい場合は --delete-after を追加
   python scripts/textbooks/manage_html.py archive --keep-latest 0 --output-dir scripts/textbooks/raw/html_archive　--delete-after
  ```

  - `--output-dir` を学部別のフォルダに変えると、`law/` や `economics/` といった単位でアーカイブを分けられます
  - アーカイブ後にディレクトリを空の状態から始めたい場合は `--delete-after` を付けて次の学部の URL を流し込むと管理しやすくなります

## 1. 前提

- Python 3.10 以降を想定 (`scrape_syllabus.py` で [beautifulsoup4](https://pypi.org/project/beautifulsoup4/) を利用)
- 追加ライブラリ: [requests](https://pypi.org/project/requests/)、(任意) [python-slugify](https://pypi.org/project/python-slugify/)
- 入力ファイル `raw/textbooks_raw.csv` の必須カラム
  - `textbook_title` (教科書名)
  - `course_title` (授業名)
  - `campus` (BKC / OIC / KRC など)
- 任意カラム (あると自動設定できる項目)
  - `textbook_title_reading` (教科書読み仮名、ひらがな推奨)
  - `course_title_reading` (授業名読み仮名)
  - `faculty_names` (カンマ区切り "理工学部,薬学部" など)
  - `department_names`
  - `tag_names`
  - `course_code` (シラバスの開講番号など)
  - `course_category` (自動推定される「general-education / faculty-course」区分)
  - `instruction_language` (授業使用言語)
  - `note` (スクレイピング時に付与された補足メモ)
  - `authors`, `publisher`, `publication_year`, `isbn`
  - `academic_year`, `term`, `schedule`, `classroom`, `credits`, `instructors`

## 1.1 シラバス HTML の収集

### 1.1.1 手作業で保存する場合

- ブラウザで対象シラバスを開き、`Ctrl+S` で HTML を保存
- ファイルを `scripts/textbooks/raw/html/` に配置

### 1.1.2 URL リストから一括ダウンロードする場合 (推奨)

1. `scripts/textbooks/raw/syllabus_urls.sample.csv` をコピーして URL リストを作成 (必要列: `url`。あると便利な列: `course_code`, `course_title`, `file_name`)
   - または、拡張子に関係なく「1 行 1 URL」のテキストファイルを用意しても動きます (例: `https://example.com/syllabus/ABC123`)
2. 依存関係をインストール
   ```powershell
   pip install requests beautifulsoup4 python-slugify
   ```
3. ダウンロードを実行
   ```powershell
   python scripts/textbooks/fetch_syllabus.py --input scripts/textbooks/raw/syllabus_urls.csv
   ```
   - 認証が必要なポータルの場合はクッキーを渡す: `--auth-cookie "sessionid=..."`
   - 大量アクセスを避けるために `--delay 1.0` などでリクエスト間隔を調整可能
   - 保存ファイル名は `course_code`→`file_name`→`course_title`→URL 末尾 の優先順で決まります

## 1.2 シラバス HTML からの自動抽出 (任意)

スクレイピングしたシラバス HTML を `raw/html/` に保存すると、`scrape_syllabus.py` で `textbooks_raw.csv` を自動生成できます。

1. 依存関係をインストール
   ```powershell
   pip install beautifulsoup4
   ```
2. シラバスページを `scripts/textbooks/raw/html/` に用意する (手動保存または `fetch_syllabus.py` による一括取得)
3. スクリプトを実行して CSV を生成
   ```powershell
   python scripts/textbooks/scrape_syllabus.py --input scripts/textbooks/raw/html --output scripts/textbooks/raw/textbooks_raw.csv
   ```
   - `--input` に単一ファイルを指定するとそのページのみを処理します
   - 授業名 (`course_title`) や開講番号 (`course_code`) はシラバス冒頭の表から抽出され、教科書が複数ある場合は行が複製されます
   - `tag_names` には自動推定されたヒント (例: `general-education`, `multi-faculty`, `international-student`, `lang:english`) が付与されます
   - `note` には別名称や複数学部向けなどの補足情報が追記されます
4. `raw/textbooks_raw.csv` を確認し、必要に応じて列を追記・修正してください

### 1.3 自動分類ロジックの概要

- 教養・共通科目らしさを学部名・授業名のパターンから推定し、`course_category` と `tag_names` に `general-education` を付与します
- 同一授業が複数学部で開講されている場合は `multi-faculty` タグと「複数学部向け」ノートを追加します
- 授業名や備考に「留学生」「International Students」などが含まれる場合は `international-student` タグを付与します
- 授業の使用言語が HTML から読み取れた場合は `instruction_language` 列に格納し、主要言語で `lang:xxx` タグを付与します
- 同じ `course_code` で授業名が複数見つかったケースは `note` に `別名称` として残るため、後続の正規化判断に活用できます

## 2. 使い方

1. `raw/textbooks_raw.csv` を用意する (スクレイピング結果から生成する場合は上記 1.1 を参照)
2. スクリプトを実行
   ```bash
   python scripts/textbooks/prepare_textbooks.py
   ```
3. `processed/` に以下が生成される
   - `textbooks_for_import.csv` … `textbooks`テーブル向けのインポート用 CSV。教科書・授業基本情報に加え、学部 (`faculty_names`)、タグ (`tag_names`)、著者・出版社などのメタデータも含みます
     授業年度や学期、開講曜日・時限、教室、単位数、担当教員 (`instructors`) まで自動で取り込みます
   - `textbooks_for_import_minimal.csv` … クイック投入向けの 4 列版 (授業名 / 教科書名 / キャンパス / 学部)。同一授業のクラス違いは自動的にユニーク化されます
   - `textbook_relations.json` … 学部・学科・タグとの紐付けに加え、`course_code` / `course_category` / `instruction_language` / `note` / 著者・出版社などを保持

## 3. Supabase への取り込み手順

1. Supabase SQL Editor で `supabase/schema/textbooks.sql` の内容を実行し、拡張 (`pg_trgm` / `pgcrypto`) とテーブル・インデックス・トリガーを準備する
2. メインテーブルへ取り込みたい形式に応じて CSV を選択
   - 学部込みの軽量マスタだけで良い場合は `textbooks_for_import_minimal.csv`
   - メタ情報付きフルカラムを維持したい場合は `textbooks_for_import.csv`
3. 選択した CSV を Supabase Storage (例: `import/` バケット) にアップロードし、SQL エディタで以下のように実行
   ```sql
    copy textbooks (
       textbook_title,
       textbook_title_reading,
       course_title,
       course_title_reading,
       campus,
       faculty_names,
       department_names,
       tag_names,
       course_code,
       course_category,
      academic_year,
      term,
      schedule,
      classroom,
      credits,
      instructors,
       instruction_language,
       note,
       authors,
       publisher,
       publication_year,
       isbn
    )
   from 'https://<project-ref>.supabase.co/storage/v1/object/public/import/textbooks_for_import.csv'
   with (format csv, header true, encoding 'utf8');
   ```
   - `textbooks_for_import_minimal.csv` を使う場合は、`copy` の列リストを 4 列 (`course_title`, `textbook_title`, `campus`, `faculty_names`) に合わせて調整する
4. 学部・学科・タグの関連は `textbook_relations.json` を使い、
   `textbook_faculties` / `textbook_departments` / `textbook_tags` に対して
   別途スクリプトや SQL で INSERT / UPSERT する。`metadata` カラムを活用したい場合は、JSON を `textbooks` テーブルの `metadata` にまとめて `update` するのが便利です

※ `textbook_relations.json` からの投入サンプルスクリプトは未実装なので、必要に応じて追加してください。

## 4. 今後の拡張案

- `textbook_relations.json` を元に `supabase-js` で関連テーブルへ一括 UPSERT する Node スクリプト
- GitHub Actions からの定期実行 (スクレイピング → 整形 →Supabase 反映)
- ISBN や出版社などのメタ情報を `metadata` (jsonb) に入れられるよう整形ロジックを拡張
