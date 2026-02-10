# moneyforward-mcp-server

![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-blue)
![License: MIT](https://img.shields.io/badge/License-MIT-green)
![MCP](https://img.shields.io/badge/MCP-compatible-purple)

## 概要

[MoneyForward ME](https://moneyforward.com/) の資産情報を [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) 経由で取得・操作するサーバーです。

MoneyForward ME には公式 API が存在しないため、Playwright によるブラウザ自動操作でデータを取得し、FastMCP で MCP プロトコルに変換して公開します。Claude Code、Claude Desktop、Cursor など MCP 対応のクライアントから自然言語で家計データにアクセスできます。

## アーキテクチャ

```
MCP Client (Claude Code / Claude Desktop / Cursor)
        │
        │  Streamable HTTP (:8000/mcp)
        ▼
┌─────────────────────────────┐
│     FastMCP Server          │
│  ┌───────────────────────┐  │
│  │   MCP Tools (7種)     │  │
│  └───────┬───────────────┘  │
│          │                  │
│  ┌───────▼───────────────┐  │
│  │  Playwright           │  │    ┌──────────────────────┐
│  │  (Headless Chromium)  │──────▶│  MoneyForward ME     │
│  └───────────────────────┘  │    │  moneyforward.com    │
│          │                  │    └──────────────────────┘
│  ┌───────▼───────────────┐  │
│  │  SQLite Cache         │  │
│  │  (TTL: 5分)           │  │
│  └───────────────────────┘  │
└─────────────────────────────┘
```

## MCP ツール一覧

| ツール | 説明 |
|--------|------|
| `get_total_assets` | 総資産額・前日比を取得 |
| `list_recent_transactions` | 直近の入出金一覧を取得（件数指定可） |
| `get_budget_status` | 今月の予算状況（カテゴリ別内訳付き）を取得 |
| `trigger_refresh` | 連携口座の一括更新を実行 |
| `health_check` | サーバー・ブラウザ・セッションの状態確認 |
| `list_manual_accounts` | 手入力口座の一覧を取得 |
| `update_manual_account` | 手入力口座の残高を外貨→JPY換算で更新（通貨は accounts.yaml の設定に従う） |

## 必要環境

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- Chromium（Playwright が自動インストール）

## セットアップ

### 依存関係インストール

```bash
uv sync
```

### 環境変数

`.env.example` をコピーして認証情報を設定します。

```bash
cp .env.example .env
```

`.env` に MoneyForward ME のログイン情報を記入してください。

### Playwright ブラウザインストール

```bash
uv run playwright install chromium
uv run playwright install-deps chromium
```

### サーバー起動

```bash
uv run fastmcp run src/server.py --transport streamable-http --host 127.0.0.1 --port 8000
```

## 設定

### 環境変数一覧

| 変数名 | 必須 | デフォルト | 説明 |
|--------|------|-----------|------|
| `MF_EMAIL` | Yes | - | MoneyForward ログインメールアドレス |
| `MF_PASSWORD` | Yes | - | MoneyForward ログインパスワード |
| `MF_TOTP_SECRET` | Yes | - | 2FA シークレットキー（Base32, 20文字） |
| `MCP_HOST` | No | `0.0.0.0` | サーバーバインドアドレス |
| `MCP_PORT` | No | `8000` | サーバーポート |
| `MCP_AUTH_TOKEN` | No | - | MCP クライアント認証用 Bearer トークン |
| `CACHE_TTL_SECONDS` | No | `300` | キャッシュ TTL（秒） |
| `BROWSER_CONTEXT_DIR` | No | `/app/browser-context` | ブラウザセッション保存先 |
| `BROWSER_HEADLESS` | No | `true` | ヘッドレスモード |
| `CACHE_DB_PATH` | No | `/app/data/cache.db` | SQLite キャッシュ DB パス |
| `LOG_LEVEL` | No | `INFO` | ログレベル |
| `LOG_FORMAT` | No | `json` | ログ形式（`json` / `console`） |
| `SELECTORS_PATH` | No | `src/selectors.yaml` | CSS セレクタ定義ファイルパス |
| `ACCOUNTS_CONFIG_PATH` | No | `accounts.yaml` | 手入力口座設定ファイルパス |

### 手入力口座（外貨建て）

海外の金融口座を外貨建てで管理し、為替レート API で JPY 換算して MoneyForward ME に登録する機能です。`accounts.yaml` の `currency` フィールドで通貨コード（MYR, USD, EUR など）を指定します。

```bash
cp accounts.yaml.example accounts.yaml
# accounts.yaml を編集して口座情報を記入
```

`accounts.yaml` は機密情報を含むため `.gitignore` 対象です。

## Claude Code との連携

### .mcp.json

プロジェクトルートに `.mcp.json` を作成:

```json
{
  "mcpServers": {
    "moneyforward-mcp": {
      "type": "url",
      "url": "http://127.0.0.1:8000/mcp"
    }
  }
}
```

### CLI

```bash
claude mcp add moneyforward-mcp --transport http http://127.0.0.1:8000/mcp
```

## ログインについて

サーバー起動後、初めて MCP ツールを呼び出すと MoneyForward ME への自動ログインが行われます。メールアドレス・パスワード・TOTP は `.env` の設定値で自動入力されるため、通常は操作不要です。

### Email OTP を求められた場合

MoneyForward ME は新しいブラウザからのログイン時に、登録メールアドレス宛に確認コード（6桁）を送信することがあります。この場合、サーバーのログに以下のようなメッセージが表示されます:

```
otp_waiting_for_code  file=/tmp/mf-otp-code.txt
```

メールに届いた確認コードを、以下のコマンドでファイルに書き込んでください:

```bash
echo "123456" > /tmp/mf-otp-code.txt
```

サーバーがファイルを検知して自動入力します（120秒以内）。

### 2回目以降のログイン

ブラウザのセッションが `./browser-context/` に保存されるため、一度ログインに成功すれば以降は OTP なしで自動ログインされます。セッションが切れた場合のみ再度ログインが発生します。

## 開発

### テスト実行

```bash
uv run pytest
```

### リンター / 型チェック

```bash
uv run ruff check src/ tests/
uv run mypy src/
```

### プロジェクト構成

```
moneyforward-mcp-server/
├── src/
│   ├── server.py              # FastMCP サーバー（エントリポイント）
│   ├── config.py              # 設定管理（Pydantic Settings）
│   ├── selectors.yaml         # CSS セレクタ定義
│   ├── browser/
│   │   ├── auth.py            # ログイン・2FA 処理
│   │   ├── context.py         # Persistent Context 管理
│   │   └── scraper.py         # スクレイピングロジック
│   ├── cache/
│   │   └── sqlite_cache.py    # SQLite キャッシュ（TTL 付き）
│   └── tools/
│       ├── assets.py          # get_total_assets
│       ├── budget.py          # get_budget_status
│       ├── transactions.py    # list_recent_transactions
│       ├── refresh.py         # trigger_refresh
│       ├── health.py          # health_check
│       ├── manual_accounts.py # list_manual_accounts, update_manual_account
│       └── common.py          # 共通ユーティリティ
├── tests/
├── docs/
│   └── PRP.md                 # プロジェクト要件定義
├── spec/
│   └── implementation_plan.md # 実装計画
├── research/
│   └── technical_research.md  # 技術調査結果
├── learning/                  # 技術学習ノート
├── pyproject.toml
├── .env.example
└── accounts.yaml.example
```

## 技術スタック

- **[FastMCP](https://github.com/jlowin/fastmcp) 2.x** - MCP サーバーフレームワーク
- **[Playwright](https://playwright.dev/python/)** - ブラウザ自動化（Persistent Context）
- **SQLite** - キャッシュ DB（TTL: 5分）
- **[structlog](https://www.structlog.org/)** - 構造化ログ
- **[Pydantic Settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)** - 設定管理
- **[httpx](https://www.python-httpx.org/)** - 為替レート API 呼び出し
- **[pyotp](https://pyauth.github.io/pyotp/)** - TOTP 2FA 自動化

## ライセンス

[MIT License](LICENSE)
