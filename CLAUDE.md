# moneyforward-mcp-server

MoneyForward ME の資産情報を MCP 経由で取得・操作するサーバー。

## 開発環境セットアップ

```bash
uv sync --dev
uv run playwright install chromium
uv run playwright install-deps chromium
cp .env.example .env  # 編集して認証情報を設定
```

## サーバー起動

```bash
uv run fastmcp run src/server.py --transport streamable-http --host 127.0.0.1 --port 8000
```

## テスト実行

```bash
uv run pytest
```

## コード構造

```
src/
├── server.py          # FastMCP サーバー（エントリポイント）
├── config.py          # Pydantic Settings による設定管理
├── selectors.yaml     # CSS セレクタ定義（UI変更時はここを更新）
├── browser/           # ブラウザ自動化レイヤー
│   ├── auth.py        # ログイン・2FA 処理
│   ├── context.py     # Persistent Context 管理
│   └── scraper.py     # スクレイピングロジック
├── cache/
│   └── sqlite_cache.py  # SQLite キャッシュ（TTL: 5分）
└── tools/             # MCP ツール定義
    ├── assets.py      # get_total_assets
    ├── budget.py      # get_budget_status
    ├── transactions.py # list_recent_transactions
    ├── refresh.py     # trigger_refresh
    ├── health.py      # health_check
    ├── manual_accounts.py # list_manual_accounts, update_manual_account
    └── common.py      # 共通ユーティリティ
```

## セレクタ管理ルール

MoneyForward ME の UI 変更に追従するため、CSS セレクタは `src/selectors.yaml` に集約している。

- スクレイピングが壊れたら、まず `selectors.yaml` のセレクタを確認・更新する
- コード内にセレクタをハードコードしない
- セレクタ変更時はコミットメッセージに変更理由を記載する

## 手入力口座（外貨建て）

`accounts.yaml` に口座設定を記載（`accounts.yaml.example` を参照）。
このファイルは機密情報を含むため `.gitignore` 対象。

## 参照ドキュメント

- `docs/PRP.md` - プロジェクト要件定義
- `spec/implementation_plan.md` - 実装計画
- `research/technical_research.md` - 技術調査結果
- `.claude/rules/moneyforward-manual-accounts.md` - 手入力口座の操作知見
