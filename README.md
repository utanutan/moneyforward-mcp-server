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
| `update_manual_account` | 手入力口座の残高を更新（外貨の場合は JPY 換算、通貨は accounts.yaml の設定に従う） |

## 必要要件

- **Python 3.12 以上**
- [uv](https://docs.astral.sh/uv/)（推奨）または pip
- Chromium（Playwright が自動インストール）

## セットアップ

### 1. uv のインストール（未導入の場合）

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# または pip でインストール
pip install uv
```

### 2. 依存関係インストール

**uv の場合（推奨）:**

```bash
uv sync
```

**pip の場合:**

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e .
```

### 3. Playwright ブラウザインストール

```bash
uv run playwright install chromium

# Linux のみ: システム依存パッケージのインストール
uv run playwright install-deps chromium
```

pip の場合は `uv run` を省略して `playwright install chromium` を実行してください。

### 4. 環境変数の設定

```bash
cp .env.example .env
```

`.env` を編集して MoneyForward ME のログイン情報を記入してください:

- `MF_EMAIL` — MoneyForward ログインメールアドレス
- `MF_PASSWORD` — MoneyForward ログインパスワード

> **Note:** パスのデフォルト値はローカル実行向け（`./browser-context`, `./data/cache.db`）です。Docker 環境では `/app/browser-context`, `/app/data/cache.db` に変更してください。

### 5. データディレクトリの作成

```bash
mkdir -p browser-context data
```

### 6. サーバー起動

**uv の場合:**

```bash
uv run fastmcp run src/server.py --transport streamable-http --host 127.0.0.1 --port 8000
```

**pip の場合:**

```bash
fastmcp run src/server.py --transport streamable-http --host 127.0.0.1 --port 8000
```

## 設定

### 環境変数一覧

| 変数名 | 必須 | デフォルト | 説明 |
|--------|------|-----------|------|
| `MF_EMAIL` | Yes | - | MoneyForward ログインメールアドレス |
| `MF_PASSWORD` | Yes | - | MoneyForward ログインパスワード |
| `MCP_HOST` | No | `0.0.0.0` | サーバーバインドアドレス |
| `MCP_PORT` | No | `8000` | サーバーポート |
| `MCP_AUTH_TOKEN` | No | - | MCP クライアント認証用 Bearer トークン |
| `CACHE_TTL_SECONDS` | No | `300` | キャッシュ TTL（秒） |
| `BROWSER_CONTEXT_DIR` | No | `./browser-context` | ブラウザセッション保存先 |
| `BROWSER_HEADLESS` | No | `true` | ヘッドレスモード |
| `CACHE_DB_PATH` | No | `./data/cache.db` | SQLite キャッシュ DB パス |
| `LOG_LEVEL` | No | `INFO` | ログレベル |
| `LOG_FORMAT` | No | `json` | ログ形式（`json` / `console`） |
| `SELECTORS_PATH` | No | `src/selectors.yaml` | CSS セレクタ定義ファイルパス |
| `ACCOUNTS_CONFIG_PATH` | No | `accounts.yaml` | 手入力口座設定ファイルパス |

### 手入力口座

MoneyForward ME に API 連携がない口座の残高を手動管理する機能です。`accounts.yaml` の `currency` フィールドで通貨コード（JPY, USD, MYR, EUR など）を指定します。JPY の場合はそのまま登録、外貨（海外の金融口座など）の場合は為替レート API で JPY 換算して登録します。

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

サーバー起動後、初めて MCP ツールを呼び出すと MoneyForward ME への自動ログインが行われます。メールアドレス・パスワードは `.env` の設定値で自動入力されるため、通常は操作不要です。

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

## 技術スタック

- **[FastMCP](https://github.com/jlowin/fastmcp) 2.x** - MCP サーバーフレームワーク
- **[Playwright](https://playwright.dev/python/)** - ブラウザ自動化（Persistent Context）
- **SQLite** - キャッシュ DB（TTL: 5分）
- **[structlog](https://www.structlog.org/)** - 構造化ログ
- **[Pydantic Settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)** - 設定管理
- **[httpx](https://www.python-httpx.org/)** - 為替レート API 呼び出し
- **[pyotp](https://pyauth.github.io/pyotp/)** - TOTP 2FA

## ライセンス

[MIT License](LICENSE)
