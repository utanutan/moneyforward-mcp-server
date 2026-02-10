# Implementation Plan: MoneyForward ME MCP Server

> **Version:** 1.0
> **Author:** Architect-Plan Agent
> **Date:** 2026-02-01
> **Scope:** Phase 0-2 (MVP)

---

## 1. プロジェクト構造

PRP Section 12 に準拠。

```
moneyforward-mcp/
├── docker-compose.yml
├── Dockerfile
├── .env.example
├── .gitignore
├── pyproject.toml
├── uv.lock
├── src/
│   ├── server.py
│   ├── config.py
│   ├── browser/
│   │   ├── __init__.py
│   │   ├── context.py
│   │   ├── auth.py
│   │   └── scraper.py
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── assets.py
│   │   ├── transactions.py
│   │   ├── budget.py
│   │   ├── refresh.py
│   │   └── health.py
│   ├── cache/
│   │   ├── __init__.py
│   │   └── sqlite_cache.py
│   └── selectors.yaml
└── tests/
    ├── test_auth.py
    ├── test_tools.py
    └── test_cache.py
```

---

## 2. Track 分割と依存関係

```
Track A (環境構築)  ──────────────────────────────┐
  pyproject.toml, Dockerfile, docker-compose.yml, │
  .env.example, .gitignore, config.py             │
                                                   ├──→ Track C (MCPツール + キャッシュ)
Track B (ブラウザ・認証層) ────────────────────────┘     tools/*.py, cache/sqlite_cache.py,
  browser/context.py, browser/auth.py,                   server.py, selectors.yaml
  browser/scraper.py
```

- **Track A** と **Track B** は並列実行可能
- **Track C** は Track A + Track B の完了後に開始（認証・ブラウザなしではスクレイピング不可、config なしでは設定読み込み不可）

---

## 3. 技術的決定事項

| 項目 | 決定 | 根拠 |
|------|------|------|
| MCP Framework | `fastmcp<3` (2.x系) | 安定版。ツール数5-10個に十分 |
| パッケージ管理 | uv | 高速依存解決。pyproject.toml ベース |
| 非同期 | async/await 全面採用 | Playwright async API + aiosqlite + FastMCP |
| ログ | structlog (JSON出力) | 構造化ログでデバッグ容易 |
| 設定管理 | pydantic-settings | 型安全な環境変数バリデーション |
| キャッシュDB | SQLite (aiosqlite) | ゼロ設定、非同期対応 |
| Docker base | `mcr.microsoft.com/playwright/python:v1.58.0-noble` | Playwright公式、Ubuntu 24.04 |
| Transport | Streamable HTTP (`:8000/mcp`) | 双方向通信、SSEフォールバック自動 |
| セレクタ管理 | 外部YAML (`selectors.yaml`) | UI変更時にコード変更不要 |

---

## 4. Track A: 環境構築

### 4.1 `pyproject.toml`

**責務**: プロジェクトメタデータと依存関係定義

```toml
[project]
name = "moneyforward-mcp-server"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastmcp<3",
    "playwright>=1.58",
    "aiosqlite>=0.22",
    "pyotp>=2.9",
    "structlog>=24.0",
    "pydantic-settings>=2.0",
    "pyyaml>=6.0",
]

[project.optional-dependencies]
dev = [
    "ruff>=0.8",
    "mypy>=1.13",
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
]

[tool.ruff]
target-version = "py312"
line-length = 100

[tool.mypy]
python_version = "3.12"
strict = true
```

### 4.2 `Dockerfile`

**責務**: 再現可能なコンテナビルド

PRP Section 8.2 の定義に従う。主要ポイント:
- ベースイメージ: `mcr.microsoft.com/playwright/python:v1.58.0-noble`
- `uv` を `/usr/local/bin` にコピー
- `uv sync --frozen` で依存インストール
- 非rootユーザー `mfuser` で実行
- CMD: `uv run fastmcp run src/server.py --transport http --host 0.0.0.0 --port 8000`

### 4.3 `docker-compose.yml`

**責務**: サービス定義、ボリューム、ヘルスチェック

PRP Section 8.1 の定義に従う。主要ポイント:
- ポート: `127.0.0.1:8000:8000` (localhost限定)
- ボリューム: `browser-data`, `cache-data`, `log-data`
- `cap_add: SYS_ADMIN`, `seccomp=unconfined`
- ヘルスチェック: `curl -f http://localhost:8000/health`

### 4.4 `.env.example`

PRP Section 8.3 に従う。全キー定義済み、値はプレースホルダー。

### 4.5 `.gitignore`

```
.env
*.db
browser-context/
logs/
__pycache__/
.mypy_cache/
.ruff_cache/
.venv/
uv.lock
playwright/.auth/
```

### 4.6 `src/config.py`

**責務**: 全設定値の一元管理
**依存**: `pydantic-settings`

```python
class Settings(BaseSettings):
    """アプリケーション設定。.env から自動読み込み。"""

    # MoneyForward認証
    mf_email: str
    mf_password: SecretStr
    mf_totp_secret: SecretStr

    # MCPサーバー
    mcp_transport: str = "http"
    mcp_host: str = "0.0.0.0"
    mcp_port: int = 8000
    mcp_auth_token: SecretStr | None = None

    # キャッシュ
    cache_ttl_seconds: int = 300
    snapshot_interval_hours: int = 24
    cache_db_path: str = "/app/data/cache.db"

    # ブラウザ
    browser_context_dir: str = "/app/browser-context"
    browser_headless: bool = True

    # ログ
    log_level: str = "INFO"
    log_format: str = "json"

    # セレクタ
    selectors_path: str = "src/selectors.yaml"

    model_config = SettingsConfigDict(env_file=".env")
```

**実装上の注意**:
- `SecretStr` で機密値のログ出力を防止
- `model_config` で `.env` ファイルパスを指定
- シングルトンパターン: モジュールレベルで `settings = Settings()` を公開

---

## 5. Track B: ブラウザ・認証層

### 5.1 `src/browser/context.py`

**責務**: Playwright Persistent Context のライフサイクル管理
**依存**: `config.py`, `playwright.async_api`

```python
class BrowserManager:
    """Playwright ブラウザインスタンスのシングルトン管理。

    アプリ起動時に initialize() で Chromium を常駐起動し、
    各ツール呼び出し時は new_page() のみで高速応答を実現する。
    """

    _instance: ClassVar[BrowserManager | None] = None
    _playwright: Playwright | None
    _context: BrowserContext | None
    _lock: asyncio.Lock

    async def initialize(self) -> None:
        """Playwright起動 + Persistent Context作成。アプリ起動時に1回呼ぶ。"""

    async def get_context(self) -> BrowserContext:
        """現在のBrowserContextを返す。未初期化なら initialize() を呼ぶ。"""

    async def new_page(self) -> Page:
        """新しいページを作成して返す。使用後は呼び出し側で close() すること。"""

    async def shutdown(self) -> None:
        """ブラウザとPlaywrightを終了。アプリ停止時に呼ぶ。"""

    @classmethod
    def get_instance(cls) -> BrowserManager:
        """シングルトンインスタンスを返す。"""
```

**実装上の注意**:
- `asyncio.Lock` で同時アクセスを制御（シングルブラウザインスタンス）
- `launch_persistent_context()` の `user_data_dir` は `Settings.browser_context_dir`
- Chromium 引数: `--disable-blink-features=AutomationControlled`, `--no-sandbox`, `--disable-dev-shm-usage`
- コンテナ起動時に `initialize()` を呼び、Chromium を常駐させる

### 5.2 `src/browser/auth.py`

**責務**: マネーフォワード ME へのログイン・2FA・セッション管理
**依存**: `context.py`, `config.py`, `pyotp`, `selectors.yaml`

```python
class AuthManager:
    """マネーフォワード ME の認証管理。"""

    def __init__(self, browser: BrowserManager, settings: Settings): ...

    async def login(self) -> bool:
        """Email → Password → TOTP の3ステップログイン。

        Returns: ログイン成功なら True
        Raises: AuthenticationError (最大3回リトライ後)
        """

    async def is_session_valid(self) -> bool:
        """現在のセッションが有効か確認。

        マネフォのホームページにアクセスし、ログイン画面にリダイレクトされないか確認。
        """

    async def ensure_authenticated(self) -> None:
        """セッション有効性を確認し、無効なら再ログイン。

        全スクレイピング処理の前に呼ぶ。
        """

    async def _input_email(self, page: Page) -> None: ...
    async def _input_password(self, page: Page) -> None: ...
    async def _input_totp(self, page: Page) -> None: ...

    def _generate_totp(self) -> str:
        """pyotp で現在の TOTP コードを生成。"""
```

**実装上の注意**:
- リトライ: 最大3回、exponential backoff (5s, 15s, 45s)
- セレクタは `selectors.yaml` の `auth` セクションから読み込み
- ログイン成功判定: URL が `moneyforward.com/**` にマッチ
- 2FA が不要な場合（セッション再利用時）のスキップ処理

### 5.3 `src/browser/scraper.py`

**責務**: 各ページからのデータ抽出ロジック
**依存**: `context.py`, `auth.py`, `config.py`, `selectors.yaml`

```python
class MoneyForwardScraper:
    """マネーフォワード ME からデータをスクレイピング。"""

    def __init__(self, browser: BrowserManager, auth: AuthManager, selectors: dict): ...

    async def get_total_assets(self) -> dict:
        """総資産ページから資産額・前日比を取得。

        URL: https://moneyforward.com/bs/portfolio
        Returns: {"total_assets_jpy": int, "daily_change_jpy": int, "fetched_at": str}
        """

    async def get_recent_transactions(self, limit: int = 20) -> list[dict]:
        """入出金ページから直近N件の取引を取得。

        URL: https://moneyforward.com/cf
        Returns: [{"date": str, "description": str, "amount": int, "category": str, ...}]
        """

    async def trigger_account_refresh(self) -> dict:
        """口座一括更新を実行。

        URL: https://moneyforward.com/accounts
        Returns: {"status": str, "refreshed_at": str}
        """

    async def get_budget_status(self) -> dict:
        """予算ページから今月の予算消化状況を取得。

        URL: https://moneyforward.com/spending
        Returns: {"month": str, "budget": int, "spent": int, "remaining": int, "categories": [...]}
        """

    async def _navigate_and_wait(self, page: Page, url: str) -> None:
        """ページ遷移 + networkidle 待機。"""

    async def _extract_text(self, page: Page, selector: str) -> str | None:
        """セレクタでテキストを取得。見つからなければ None。"""

    async def _extract_table(self, page: Page, selector: str) -> list[dict]:
        """テーブル要素をパースして辞書リストに変換。"""
```

**実装上の注意**:
- 各メソッドの先頭で `auth.ensure_authenticated()` を呼ぶ
- `page.wait_for_load_state("networkidle")` でSPAの描画完了を待つ
- 金額文字列のパース: `"¥1,234,567"` → `1234567` (int)
- 各メソッドは1ページ=1操作。ページは使用後に必ず `close()`
- スクレイピング失敗時は `ToolError` を raise

---

## 6. Track C: MCPツール + キャッシュ

### 6.1 `src/cache/sqlite_cache.py`

**責務**: TTL付きキャッシュ + 日次スナップショット保存
**依存**: `aiosqlite`, `config.py`

```python
class CacheManager:
    """SQLite ベースの TTL キャッシュ + スナップショット管理。"""

    def __init__(self, db_path: str, default_ttl: int = 300): ...

    async def initialize(self) -> None:
        """テーブル作成 (cache, daily_asset_snapshots, account_snapshots, spending_snapshots, snapshot_metadata)。"""

    # --- TTL キャッシュ ---
    async def get(self, key: str) -> Any | None:
        """キャッシュ取得。TTL超過ならNone。"""

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """キャッシュ設定。value は JSON シリアライズ。"""

    async def delete(self, key: str) -> None: ...

    async def cleanup_expired(self) -> int:
        """期限切れエントリを削除。削除件数を返す。"""

    # --- 日次スナップショット ---
    async def save_daily_snapshot(self, snapshot_date: date, total_assets: int, total_liabilities: int, net_worth: int) -> None: ...

    async def save_account_snapshots(self, snapshot_date: date, accounts: list[dict]) -> None: ...

    async def get_asset_history(self, start_date: date, end_date: date) -> list[dict]:
        """指定期間の資産推移を返す。"""
```

**スキーマ**: 技術調査 Section 4.3.1 に準拠（`cache`, `daily_asset_snapshots`, `account_snapshots`, `spending_snapshots`, `snapshot_metadata`）

**実装上の注意**:
- DB接続はアプリ起動時に1つ保持（長期接続でページキャッシュを活用）
- `asyncio.Lock` で書き込みの排他制御
- スナップショット保存はトランザクションで一括コミット

### 6.2 `src/tools/assets.py`

**責務**: `get_total_assets` ツール
**依存**: `scraper.py`, `cache/sqlite_cache.py`

```python
@mcp.tool
async def get_total_assets() -> dict:
    """現在の総資産額と前日比を取得する。
    マネーフォワードMEのホーム画面から最新の資産情報をスクレイピングする。
    キャッシュがあればキャッシュを返却（TTL: 5分）。
    """
```

**レスポンス形式** (PRP F-4準拠):
```json
{
  "status": "success",
  "data": {
    "total_assets_jpy": 5000000,
    "daily_change_jpy": 12000
  },
  "metadata": {
    "fetched_at": "2026-02-01T10:30:00+09:00",
    "source": "scraping",
    "cached": false,
    "cache_ttl_seconds": 300
  }
}
```

### 6.3 `src/tools/transactions.py`

**責務**: `list_recent_transactions` ツール
**依存**: `scraper.py`, `cache/sqlite_cache.py`

```python
@mcp.tool
async def list_recent_transactions(limit: int = 20) -> dict:
    """直近N件の入出金履歴を取得する。
    デフォルトは直近20件。最大100件まで指定可能。
    """
```

### 6.4 `src/tools/budget.py`

**責務**: `get_budget_status` ツール
**依存**: `scraper.py`, `cache/sqlite_cache.py`

```python
@mcp.tool
async def get_budget_status() -> dict:
    """今月の予算消化状況を取得する。
    カテゴリ別の予算と実績、残り予算額を返す。
    """
```

### 6.5 `src/tools/refresh.py`

**責務**: `trigger_refresh` ツール
**依存**: `scraper.py`

```python
@mcp.tool
async def trigger_refresh() -> dict:
    """連携口座の一括更新をトリガーする。
    更新完了まで待機し、結果を返す。
    """
```

**実装上の注意**:
- 一括更新は時間がかかるため、タイムアウトを長めに設定（30秒）
- キャッシュは使わない（常にリアルタイム操作）

### 6.6 `src/tools/health.py`

**責務**: `health_check` ツール
**依存**: `auth.py`, `cache/sqlite_cache.py`

```python
@mcp.tool
async def health_check() -> dict:
    """MCPサーバーとマネフォセッションの健全性を確認する。
    ブラウザ状態、セッション有効性、キャッシュDB接続を確認。
    """
```

### 6.7 `src/server.py`

**責務**: FastMCPサーバーのエントリポイント。ツール登録、ライフサイクル管理
**依存**: 全モジュール

```python
from fastmcp import FastMCP
import structlog

mcp = FastMCP(
    "MoneyForward MCP Server",
    mask_error_details=True,
)

# ツール登録
from src.tools.assets import get_total_assets
from src.tools.transactions import list_recent_transactions
from src.tools.budget import get_budget_status
from src.tools.refresh import trigger_refresh
from src.tools.health import health_check

# ライフサイクル管理
@mcp.on_startup
async def startup():
    """ブラウザ初期化、キャッシュDB初期化、structlog設定。"""

@mcp.on_shutdown
async def shutdown():
    """ブラウザ終了、DB接続クローズ。"""
```

**実装上の注意**:
- `@mcp.tool` デコレータは各 `tools/*.py` で使用し、`server.py` でインポート
- `structlog` の設定は `startup` で実行（JSON出力、レベルは `Settings.log_level`）
- FastMCP の `on_startup` / `on_shutdown` フックでリソース管理

### 6.8 `src/selectors.yaml`

**責務**: マネフォ各ページのCSSセレクタ外部定義

---

## 7. selectors.yaml 設計

```yaml
# MoneyForward ME CSS Selectors
# UI変更時はこのファイルのみ更新する

auth:
  login_url: "https://id.moneyforward.com/sign_in"
  email_input: 'input[name="mfid_user[email]"]'
  password_input: 'input[name="mfid_user[password]"]'
  totp_input: 'input[name="otp"]'
  submit_button: 'button[type="submit"]'
  login_success_url_pattern: "https://moneyforward.com/**"

assets:
  url: "https://moneyforward.com/bs/portfolio"
  total_assets: "TODO_SELECTOR"          # 総資産額の要素
  daily_change: "TODO_SELECTOR"          # 前日比の要素
  asset_breakdown:                        # 資産内訳テーブル
    table: "TODO_SELECTOR"
    row: "TODO_SELECTOR"
    name: "TODO_SELECTOR"
    value: "TODO_SELECTOR"

transactions:
  url: "https://moneyforward.com/cf"
  table: "TODO_SELECTOR"                 # 入出金テーブル
  row: "TODO_SELECTOR"                   # 各行
  columns:
    date: "TODO_SELECTOR"
    description: "TODO_SELECTOR"
    amount: "TODO_SELECTOR"
    category: "TODO_SELECTOR"
    account: "TODO_SELECTOR"
  pagination:
    next_button: "TODO_SELECTOR"

budget:
  url: "https://moneyforward.com/spending"
  total_budget: "TODO_SELECTOR"          # 予算合計
  total_spent: "TODO_SELECTOR"           # 支出合計
  remaining: "TODO_SELECTOR"             # 残額
  categories:
    table: "TODO_SELECTOR"
    row: "TODO_SELECTOR"
    name: "TODO_SELECTOR"
    budget_amount: "TODO_SELECTOR"
    spent_amount: "TODO_SELECTOR"

refresh:
  url: "https://moneyforward.com/accounts"
  sync_button: "TODO_SELECTOR"           # 一括更新ボタン
  sync_status: "TODO_SELECTOR"           # 更新ステータス表示
  last_updated: "TODO_SELECTOR"          # 最終更新日時

session_check:
  # セッション有効性チェック用
  logged_in_indicator: "TODO_SELECTOR"   # ログイン済みを示す要素（ユーザー名表示等）
```

**注意**: `TODO_SELECTOR` は実際のマネフォ画面のDOM解析後に埋める。Phase 1 の認証プロトタイプ完成後、ブラウザで各ページのDOMを調査してセレクタを確定する。

---

## 8. 共通パターン

### 8.1 統一レスポンス形式

全ツールは以下のヘルパーを使う:

```python
def success_response(data: dict, source: str = "scraping", cached: bool = False) -> dict:
    return {
        "status": "success",
        "data": data,
        "metadata": {
            "fetched_at": datetime.now(timezone(timedelta(hours=9))).isoformat(),
            "source": source,
            "cached": cached,
            "cache_ttl_seconds": settings.cache_ttl_seconds,
        }
    }

def error_response(message: str, code: str = "UNKNOWN_ERROR") -> dict:
    return {
        "status": "error",
        "error": {"code": code, "message": message},
        "metadata": {"fetched_at": datetime.now(timezone(timedelta(hours=9))).isoformat()}
    }
```

### 8.2 キャッシュ付きツールパターン

```python
async def cached_tool(cache_key: str, scrape_fn, **kwargs) -> dict:
    cached = await cache.get(cache_key)
    if cached:
        return success_response(cached, cached=True)
    try:
        data = await scrape_fn(**kwargs)
        await cache.set(cache_key, data)
        return success_response(data)
    except Exception as e:
        # スクレイピング失敗時、期限切れキャッシュがあればそれを返す
        stale = await cache.get_stale(cache_key)
        if stale:
            return success_response(stale, cached=True)
        raise ToolError(str(e))
```

### 8.3 金額パースユーティリティ

```python
def parse_currency(text: str) -> int:
    """'¥1,234,567' や '-¥12,345' を int に変換。"""
```

---

## 9. 実装順序（タスク一覧）

### Phase 0: 環境構築 (Track A)

| # | ファイル | タスク |
|---|---------|--------|
| A-1 | `pyproject.toml` | プロジェクト初期化、依存定義 |
| A-2 | `.gitignore` | 除外パターン設定 |
| A-3 | `.env.example` | 環境変数テンプレート |
| A-4 | `src/config.py` | Pydantic Settings クラス |
| A-5 | `Dockerfile` | コンテナビルド定義 |
| A-6 | `docker-compose.yml` | サービス定義 |

### Phase 1: 認証プロトタイプ (Track B)

| # | ファイル | タスク | 依存 |
|---|---------|--------|------|
| B-1 | `src/browser/__init__.py` | パッケージ初期化 | A-1 |
| B-2 | `src/browser/context.py` | BrowserManager クラス | A-4 |
| B-3 | `src/browser/auth.py` | AuthManager クラス | B-2 |
| B-4 | `src/selectors.yaml` | セレクタ定義（auth セクション確定、他は TODO） | - |
| B-5 | `src/browser/scraper.py` | MoneyForwardScraper クラス | B-2, B-3, B-4 |

### Phase 2: MCPツール + キャッシュ (Track C)

| # | ファイル | タスク | 依存 |
|---|---------|--------|------|
| C-1 | `src/cache/__init__.py` | パッケージ初期化 | A-1 |
| C-2 | `src/cache/sqlite_cache.py` | CacheManager クラス | A-4 |
| C-3 | `src/tools/__init__.py` | パッケージ初期化 | A-1 |
| C-4 | `src/tools/health.py` | health_check ツール | B-3, C-2 |
| C-5 | `src/tools/assets.py` | get_total_assets ツール | B-5, C-2 |
| C-6 | `src/tools/transactions.py` | list_recent_transactions ツール | B-5, C-2 |
| C-7 | `src/tools/budget.py` | get_budget_status ツール | B-5, C-2 |
| C-8 | `src/tools/refresh.py` | trigger_refresh ツール | B-5 |
| C-9 | `src/server.py` | FastMCPサーバー統合 | C-4〜C-8 |

---

## 10. Phase 3以降（将来対応 - 概要のみ）

### Phase 3: 堅牢化
- Bearer Token認証のFastMCPへの組み込み
- cronによる日次スナップショット自動取得
- セレクタ変更の自動検知とアラート通知
- Tailscale VPN設定

### Phase 4: マレーシア拡張
- `src/tools/malaysia.py`: Notion API連携、為替レート取得
- `get_myr_assets`, `get_combined_net_worth` ツール

### Phase 5: 運用・監視
- LINE/Discord通知
- `get_asset_history` (キャッシュベース推移)
- `get_monthly_summary`, `get_category_breakdown`
- 運用ドキュメント整備
