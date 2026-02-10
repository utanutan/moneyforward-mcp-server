# Technical Research Report
## マネーフォワード ME MCP Server 技術調査

**調査日**: 2026-02-01
**調査者**: Researcher Agent

---

## 1. FastMCP 2.x (Python)

### 1.1 概要

FastMCP 2.0 は、Model Context Protocol (MCP) サーバーとクライアントを Python で構築するための本番環境対応フレームワークです。

### 1.2 インストール方法

```bash
pip install fastmcp
```

バージョン 3.0 の破壊的変更を避けるため、v2 に固定する場合:

```bash
pip install 'fastmcp<3'
```

### 1.3 `@mcp.tool` デコレータの使い方

`@mcp.tool` デコレータは、Python 関数を LLM に公開するための主要な方法です。型ヒントと docstring に基づいて、MCP スキーマが自動生成されます。

#### 基本例

```python
from fastmcp import FastMCP

mcp = FastMCP("My App")

@mcp.tool()
def add(a: int, b: int) -> int:
    """Add two numbers"""
    return a + b
```

#### Context インジェクション付き

Context にアクセスするには、`Context` 型のパラメータを追加します:

```python
from fastmcp import FastMCP, Context

mcp = FastMCP("My MCP Server")

@mcp.tool
async def process_data(uri: str, ctx: Context):
    await ctx.info(f"Processing {uri}...")
    data = await ctx.read_resource(uri)
    return summary.text
```

### 1.4 HTTP Transport での起動方法

FastMCP 2.0 は HTTP ベースのトランスポートをサポートしています。以下の方法で起動できます:

```python
from fastmcp import FastMCP

mcp = FastMCP("My HTTP Server")

# HTTP アプリケーションの取得
app = mcp.http_app()

# Uvicorn などの ASGI サーバーで起動
# uvicorn main:app --host 0.0.0.0 --port 8000
```

### 1.5 Bearer Token 認証の実装方法

#### クライアント側の実装

最も簡単な方法は、既存の Bearer トークンを `auth` パラメータに文字列として渡すことです:

```python
from fastmcp import Client
from fastmcp.transport import StreamableHttpTransport

# 方法1: シンプルな文字列トークン
client = Client(
    url="https://api.example.com",
    auth="your-bearer-token-here"
)

# 方法2: トランスポートレベルの認証
transport = StreamableHttpTransport(
    url="https://api.example.com",
    auth="your-bearer-token-here"
)
client = Client(transport=transport)

# 方法3: 明示的な BearerAuth クラス
from fastmcp.auth import BearerAuth
client = Client(
    url="https://api.example.com",
    auth=BearerAuth(token="your-bearer-token-here")
)
```

#### サーバー側の実装

```python
from fastmcp import FastMCP
from fastmcp.server.auth import BearerAuthProvider

# BearerAuthProvider の設定
auth_provider = BearerAuthProvider(
    jwks_uri="https://login.microsoftonline.com/{tenant}/discovery/v2.0/keys",
    issuer="https://login.microsoftonline.com/{tenant}/v2.0",
    audience="api://{client_id}",
    required_scopes=["api.access"]
)

mcp = FastMCP("Secure Server", auth=auth_provider)
```

#### セキュリティ機能 (2025-2026)

- JWT トークンによるトークンベースセキュリティ
- RSA キーペアを使用した非対称暗号化
- HTTP streamable と SSE (Server-Sent Events) 両方のトランスポートサポート

### 1.6 エラーハンドリングのベストプラクティス

#### ToolError の使用

`ToolError` は、明確で実行可能なメッセージを LLM に送信するための特別な例外です:

```python
from fastmcp import FastMCP, ToolError

@mcp.tool
def divide(a: float, b: float) -> float:
    if b == 0:
        raise ToolError("Cannot divide by zero")
    return a / b
```

#### 特定の例外タイプのハンドリング

各エラータイプに対して具体的なメッセージを設定します:

```python
from fastmcp import FastMCP, ToolError
import json

@mcp.tool
def read_json(filepath: str) -> dict:
    try:
        with open(filepath) as f:
            return json.load(f)
    except FileNotFoundError:
        raise ToolError(f"File not found: {filepath}")
    except json.JSONDecodeError:
        raise ToolError(f"Invalid JSON in: {filepath}")
```

#### 本番環境での内部エラーのマスキング

```python
mcp = FastMCP("SecureServer", mask_error_details=True)

@mcp.tool
def query_database(sql: str) -> list:
    if "DROP" in sql.upper():
        raise ToolError("DROP statements not allowed")  # クライアントに送信
    return db.execute(sql)  # これが失敗した場合、汎用エラーが表示される
```

#### エラーハンドリングミドルウェア

FastMCP は、一貫したエラーハンドリングとロギングを提供するミドルウェアを備えています。例外をキャッチし、適切にログを記録し、適切な MCP エラーレスポンスに変換します。

### 1.7 主要機能

- 高度な MCP パターン（サーバー構成、プロキシ、OpenAPI/FastAPI 生成、ツール変換）
- エンタープライズ認証（Google、GitHub、WorkOS、Azure、Auth0 など）
- デプロイメントツール
- テストユーティリティ
- 包括的なクライアントライブラリ

---

## 2. Playwright Python - Persistent Context

### 2.1 `launch_persistent_context()` API 仕様

`launch_persistent_context()` は、`user_data_dir` に配置された永続ストレージを使用するブラウザを起動し、唯一のコンテキストを返します。このコンテキストを閉じると、ブラウザも自動的に閉じます。

#### 主要パラメータ

| パラメータ | 説明 |
|-----------|------|
| `user_data_dir` | Cookie やローカルストレージなどのブラウザセッションデータを保存するユーザーデータディレクトリへのパス。空の文字列を渡すと、一時ディレクトリが作成されます。 |
| `timeout` | ブラウザインスタンスの起動を待つ最大時間（ミリ秒）。デフォルトは 30000 (30秒)。タイムアウトを無効にするには 0 を渡します。 |
| `headless` | ヘッドレスモードで実行するかどうか。デフォルトは `True`。 |

#### 基本的な使用例

```python
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    context = p.chromium.launch_persistent_context(
        user_data_dir="playwright_cache",  # セッションを保存するフォルダ
        headless=True  # ヘッドレスモードで実行
    )
    page = context.new_page()
    page.goto("https://example.com/login")
    # ... ログイン処理 ...
    context.close()
```

#### 非同期版

```python
from playwright.async_api import async_playwright

async with async_playwright() as p:
    context = await p.chromium.launch_persistent_context(
        user_data_dir="playwright_cache",
        headless=True
    )
    page = await context.new_page()
    await page.goto("https://example.com/login")
    # ... 処理 ...
    await context.close()
```

### 2.2 Docker 環境での利用方法

#### 利用可能な Docker イメージ

現在の Playwright Python Docker イメージ:

- `mcr.microsoft.com/playwright/python:v1.57.0` - Ubuntu 24.04 LTS (Noble Numbat) ベース
- `mcr.microsoft.com/playwright/python:v1.57.0-noble`
- `mcr.microsoft.com/playwright/python:v1.57.0-jammy` - Ubuntu 22.04 LTS (Jammy Jellyfish)
- `mcr.microsoft.com/playwright/python:v1.58.0-noble` - 最新版

**重要**: Docker イメージのバージョンとプロジェクトの Playwright バージョンを一致させることを推奨します。バージョンが一致しない場合、Playwright はブラウザの実行可能ファイルを見つけられません。

#### Dockerfile 例

```dockerfile
FROM mcr.microsoft.com/playwright/python:v1.58.0-noble

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

CMD ["python", "main.py"]
```

#### Docker での実行

```bash
docker build -t my-playwright-app .
docker run -v $(pwd)/playwright_cache:/app/playwright_cache my-playwright-app
```

#### セキュリティに関する注意

デフォルトでは、Docker イメージは root ユーザーを使用してブラウザを実行するため、Chromium のサンドボックスは無効になります。本番環境では、非 root ユーザーを使用することを推奨します。

### 2.3 セッション永続化のベストプラクティス

#### 1. ディレクトリ管理

- アカウント/環境ごとに別々の `user_data_dir` を使用する
- 異なるスクリプト間で永続キャッシュを共有しない
- `playwright/.auth` ディレクトリを作成し、`.gitignore` に追加する

```python
import os

USER_DATA_DIR = os.path.join(os.getcwd(), "playwright", ".auth", "session1")
os.makedirs(USER_DATA_DIR, exist_ok=True)

context = p.chromium.launch_persistent_context(
    user_data_dir=USER_DATA_DIR,
    headless=True
)
```

#### 2. セキュリティ考慮事項

ブラウザステートファイルには、あなたやテストアカウントになりすますために使用できる機密性の高い Cookie やヘッダーが含まれている可能性があります。**プライベートまたはパブリックリポジトリにコミットすることは避けてください。**

```gitignore
# .gitignore
playwright/.auth/
playwright_cache/
```

#### 3. 環境適性

永続認証はディスクの場所に依存するため、**CI 環境には適していません**。CI では、各実行でログインを行うか、API トークンを使用してください。

#### 4. Chrome のユーザープロファイルに関する注意

最近の Chrome ポリシー変更により、デフォルトの Chrome ユーザープロファイルの自動化はサポートされていません。`userDataDir` を Chrome のメイン「User Data」ディレクトリに指定すると、ページが読み込まれないか、ブラウザが終了する可能性があります。**自動化プロファイル用に別のディレクトリを作成して使用してください。**

### 2.4 ヘッドレスモードでの注意点

#### デバッグ時

```python
context = p.chromium.launch_persistent_context(
    user_data_dir="playwright_cache",
    headless=False,  # デバッグ時は False に設定
    slow_mo=1000  # 操作を 1 秒遅延させる
)
```

#### 本番環境

```python
context = p.chromium.launch_persistent_context(
    user_data_dir="playwright_cache",
    headless=True,  # 本番では True に設定
    args=[
        '--disable-blink-features=AutomationControlled',  # 自動化検出を回避
        '--no-sandbox',  # Docker 環境で必要な場合
        '--disable-dev-shm-usage'  # 共有メモリの問題を回避
    ]
)
```

### 2.5 利点

- ログイン済みセッションを再利用することで、各テストで繰り返しログイン操作を実行するオーバーヘッドを回避できます
- テスト時間の短縮
- 自動化ワークフローの簡素化

### 2.6 最新アップデート (2026)

- `firefox_user_prefs` オプションが `browser_type.launch_persistent_context()` に追加されました

---

## 3. マネーフォワード ME スクレイピング

### 3.1 概要

マネーフォワード ME は、銀行口座、クレジットカード、投資を一つのインターフェースから管理できる個人向け財務管理ソフトウェアです。

### 3.2 ログインフロー

#### 3.2.1 基本フロー

1. **Email 入力**: ログインページでメールアドレスを入力
2. **Password 入力**: パスワードを入力
3. **2FA (TOTP)**: pyotp を使用した TOTP コードの自動生成と入力

#### 3.2.2 実装例 (概念)

```python
from playwright.async_api import async_playwright
import pyotp

async def login_to_moneyforward(email: str, password: str, totp_secret: str):
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir="./mf_session",
            headless=True
        )
        page = await context.new_page()

        # ログインページに移動
        await page.goto("https://id.moneyforward.com/sign_in")

        # Email 入力
        await page.fill('input[name="mfid_user[email]"]', email)
        await page.click('button[type="submit"]')

        # Password 入力
        await page.wait_for_selector('input[name="mfid_user[password]"]')
        await page.fill('input[name="mfid_user[password]"]', password)
        await page.click('button[type="submit"]')

        # 2FA が必要な場合
        try:
            await page.wait_for_selector('input[name="otp"]', timeout=3000)

            # pyotp で TOTP コードを生成
            totp = pyotp.TOTP(totp_secret)
            otp_code = totp.now()

            await page.fill('input[name="otp"]', otp_code)
            await page.click('button[type="submit"]')
        except:
            pass  # 2FA が不要な場合

        # ログイン成功を確認
        await page.wait_for_url("https://moneyforward.com/**")

        await context.close()
```

### 3.3 主要ページの URL 構造

マネーフォワード ME の主要ページ URL（推定）:

| ページ | URL |
|--------|-----|
| ホーム/資産 | `https://moneyforward.com/bs/portfolio` |
| 入出金 | `https://moneyforward.com/cf` |
| 予算 | `https://moneyforward.com/spending` |
| 口座一括更新 | `https://moneyforward.com/accounts/sync` または API エンドポイント |

**注意**: これらの URL は一般的なパターンに基づく推定です。実際の URL 構造は、マネーフォワード ME の最新のウェブインターフェースを確認する必要があります。

### 3.4 pyotp による TOTP 自動生成

#### 3.4.1 pyotp の概要

PyOTP は、ワンタイムパスワードを生成および検証するための Python ライブラリです。RFC 4226 (HOTP) と RFC 6238 (TOTP) の標準を実装しています。

#### 3.4.2 インストール

```bash
pip install pyotp
```

#### 3.4.3 基本的な使用方法

```python
import pyotp

# シークレットキーから TOTP オブジェクトを作成
totp_secret = "JBSWY3DPEHPK3PXP"  # 2FA 設定時に取得したシークレット
totp = pyotp.TOTP(totp_secret)

# 現在の TOTP コードを生成
current_otp = totp.now()
print(f"Current OTP: {current_otp}")

# 特定の時刻の TOTP コードを生成
otp_at_time = totp.at(1649000000)  # Unix タイムスタンプ
```

#### 3.4.4 TOTP の仕組み

TOTP は、共有シークレットと現在時刻を組み合わせてワンタイムパスワードを生成します:

- デフォルトでは 30 秒間隔で新しい OTP が生成されます
- シークレットと現在時刻を使用して、各間隔ごとに新しい OTP を生成
- Google Authenticator、Authy などの OTP アプリと互換性があります

#### 3.4.5 マネーフォワード ME での使用例

```python
import pyotp
import os

# 環境変数からシークレットを取得（セキュリティのため）
MF_TOTP_SECRET = os.getenv("MF_TOTP_SECRET")

def get_mf_totp_code() -> str:
    """マネーフォワード ME の現在の TOTP コードを取得"""
    totp = pyotp.TOTP(MF_TOTP_SECRET)
    return totp.now()

# 使用例
otp_code = get_mf_totp_code()
print(f"OTP Code: {otp_code}")
```

#### 3.4.6 セキュリティのベストプラクティス

- **シークレットキーを環境変数に保存**: コードにハードコードしない
- **`.env` ファイルを使用**: `.gitignore` に追加する
- **暗号化**: 可能であれば、シークレットキーを暗号化して保存

```python
from dotenv import load_dotenv
import os
import pyotp

load_dotenv()  # .env ファイルから環境変数をロード

totp_secret = os.getenv("MF_TOTP_SECRET")
totp = pyotp.TOTP(totp_secret)
current_otp = totp.now()
```

---

## 4. SQLite キャッシュ設計

### 4.1 Python aiosqlite の使い方

#### 4.1.1 概要

aiosqlite は、標準の sqlite3 モジュールへの asyncio ブリッジです。メイン AsyncIO イベントループで SQLite データベースと対話でき、他のコルーチンの実行をブロックしません。

- Python 3.8 以降と互換性
- 接続ごとに単一の共有スレッドを使用
- 標準 SQLite 操作の非同期版を提供

#### 4.1.2 インストール

```bash
pip install aiosqlite
```

#### 4.1.3 基本的な使用方法

```python
import aiosqlite

async def basic_example():
    async with aiosqlite.connect("database.db") as db:
        # テーブル作成
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT UNIQUE
            )
        """)
        await db.commit()

        # データ挿入
        await db.execute(
            "INSERT INTO users (name, email) VALUES (?, ?)",
            ("Alice", "alice@example.com")
        )
        await db.commit()

        # データ取得
        async with db.execute("SELECT * FROM users") as cursor:
            async for row in cursor:
                print(row)
```

#### 4.1.4 重要な変更 (v0.22.0 以降)

v0.22.0 から、`aiosqlite.Connection` オブジェクトは `threading.Thread` を継承しなくなりました。コンテキストマネージャとして使用しない場合、クライアントは `await connection.close()` または `connection.stop()` を呼び出す必要があります。

```python
# v0.22.0 以降
db = await aiosqlite.connect("database.db")
try:
    # データベース操作
    await db.execute("...")
    await db.commit()
finally:
    await db.close()  # 必須
```

### 4.2 TTL 付きキャッシュの実装パターン

#### 4.2.1 cachetools ライブラリを使用した TTL キャッシュ

```python
from cachetools import TTLCache
from functools import wraps

# メモリ内 TTL キャッシュ
cache = TTLCache(maxsize=1024, ttl=600)  # 10分間のTTL

def cached(cache):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            key = str(args) + str(kwargs)
            if key in cache:
                return cache[key]
            result = await func(*args, **kwargs)
            cache[key] = result
            return result
        return wrapper
    return decorator

@cached(cache)
async def get_weather_data(city: str):
    # API 呼び出しなど
    return {"city": city, "temp": 20}
```

#### 4.2.2 SQLite ベースの TTL キャッシュ

```python
import aiosqlite
import time
import json
from typing import Any, Optional

class SQLiteTTLCache:
    def __init__(self, db_path: str, default_ttl: int = 3600):
        self.db_path = db_path
        self.default_ttl = default_ttl

    async def initialize(self):
        """キャッシュテーブルを初期化"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS cache (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    expires_at INTEGER NOT NULL
                )
            """)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_expires_at
                ON cache(expires_at)
            """)
            await db.commit()

    async def set(self, key: str, value: Any, ttl: Optional[int] = None):
        """キャッシュに値を設定"""
        ttl = ttl or self.default_ttl
        expires_at = int(time.time()) + ttl
        value_json = json.dumps(value)

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO cache (key, value, expires_at) VALUES (?, ?, ?)",
                (key, value_json, expires_at)
            )
            await db.commit()

    async def get(self, key: str) -> Optional[Any]:
        """キャッシュから値を取得"""
        current_time = int(time.time())

        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT value, expires_at FROM cache WHERE key = ?",
                (key,)
            ) as cursor:
                row = await cursor.fetchone()

                if not row:
                    return None

                value_json, expires_at = row

                # 有効期限切れをチェック
                if expires_at < current_time:
                    await self.delete(key)
                    return None

                return json.loads(value_json)

    async def delete(self, key: str):
        """キャッシュから値を削除"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM cache WHERE key = ?", (key,))
            await db.commit()

    async def cleanup_expired(self):
        """期限切れのエントリを削除"""
        current_time = int(time.time())

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "DELETE FROM cache WHERE expires_at < ?",
                (current_time,)
            )
            await db.commit()

# 使用例
async def main():
    cache = SQLiteTTLCache("cache.db", default_ttl=600)
    await cache.initialize()

    # キャッシュに設定
    await cache.set("user:123", {"name": "Alice", "email": "alice@example.com"}, ttl=300)

    # キャッシュから取得
    user_data = await cache.get("user:123")
    print(user_data)

    # 期限切れエントリのクリーンアップ
    await cache.cleanup_expired()
```

### 4.3 日次スナップショットのスキーマ設計

#### 4.3.1 基本スキーマ

```sql
-- 日次資産スナップショット
CREATE TABLE IF NOT EXISTS daily_asset_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_date DATE NOT NULL UNIQUE,
    total_assets INTEGER NOT NULL,
    total_liabilities INTEGER NOT NULL,
    net_worth INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_snapshot_date ON daily_asset_snapshots(snapshot_date);

-- 口座別詳細スナップショット
CREATE TABLE IF NOT EXISTS account_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_date DATE NOT NULL,
    account_id TEXT NOT NULL,
    account_name TEXT NOT NULL,
    account_type TEXT NOT NULL,  -- 'bank', 'credit_card', 'investment', etc.
    balance INTEGER NOT NULL,
    currency TEXT DEFAULT 'JPY',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(snapshot_date, account_id)
);

CREATE INDEX idx_account_snapshot_date ON account_snapshots(snapshot_date);
CREATE INDEX idx_account_id ON account_snapshots(account_id);

-- カテゴリ別支出スナップショット
CREATE TABLE IF NOT EXISTS spending_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_date DATE NOT NULL,
    category TEXT NOT NULL,
    amount INTEGER NOT NULL,
    transaction_count INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(snapshot_date, category)
);

CREATE INDEX idx_spending_snapshot_date ON spending_snapshots(snapshot_date);

-- メタデータ管理
CREATE TABLE IF NOT EXISTS snapshot_metadata (
    snapshot_date DATE PRIMARY KEY,
    status TEXT NOT NULL,  -- 'pending', 'completed', 'failed'
    data_source TEXT NOT NULL,  -- 'scraping', 'api', 'manual'
    error_message TEXT,
    started_at TIMESTAMP,
    completed_at TIMESTAMP
);
```

#### 4.3.2 実装例

```python
import aiosqlite
from datetime import date, datetime
from typing import List, Dict, Any

class DailySnapshotManager:
    def __init__(self, db_path: str):
        self.db_path = db_path

    async def initialize(self):
        """データベーススキーマを初期化"""
        async with aiosqlite.connect(self.db_path) as db:
            # 上記の CREATE TABLE 文を実行
            await db.executescript("""
                -- ここに上記の CREATE TABLE 文を配置
            """)
            await db.commit()

    async def save_daily_snapshot(
        self,
        snapshot_date: date,
        total_assets: int,
        total_liabilities: int,
        net_worth: int
    ):
        """日次資産スナップショットを保存"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT OR REPLACE INTO daily_asset_snapshots
                (snapshot_date, total_assets, total_liabilities, net_worth, updated_at)
                VALUES (?, ?, ?, ?, ?)
            """, (snapshot_date, total_assets, total_liabilities, net_worth, datetime.now()))
            await db.commit()

    async def save_account_snapshots(
        self,
        snapshot_date: date,
        accounts: List[Dict[str, Any]]
    ):
        """口座別スナップショットを保存"""
        async with aiosqlite.connect(self.db_path) as db:
            for account in accounts:
                await db.execute("""
                    INSERT OR REPLACE INTO account_snapshots
                    (snapshot_date, account_id, account_name, account_type, balance, currency)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    snapshot_date,
                    account['id'],
                    account['name'],
                    account['type'],
                    account['balance'],
                    account.get('currency', 'JPY')
                ))
            await db.commit()

    async def save_spending_snapshot(
        self,
        snapshot_date: date,
        spending_by_category: Dict[str, Dict[str, int]]
    ):
        """カテゴリ別支出スナップショットを保存"""
        async with aiosqlite.connect(self.db_path) as db:
            for category, data in spending_by_category.items():
                await db.execute("""
                    INSERT OR REPLACE INTO spending_snapshots
                    (snapshot_date, category, amount, transaction_count)
                    VALUES (?, ?, ?, ?)
                """, (
                    snapshot_date,
                    category,
                    data['amount'],
                    data['count']
                ))
            await db.commit()

    async def get_snapshot_for_date(self, snapshot_date: date) -> Dict[str, Any]:
        """特定の日付のスナップショットを取得"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row

            # 資産スナップショット
            async with db.execute(
                "SELECT * FROM daily_asset_snapshots WHERE snapshot_date = ?",
                (snapshot_date,)
            ) as cursor:
                asset_snapshot = await cursor.fetchone()

            # 口座スナップショット
            async with db.execute(
                "SELECT * FROM account_snapshots WHERE snapshot_date = ?",
                (snapshot_date,)
            ) as cursor:
                account_snapshots = await cursor.fetchall()

            # 支出スナップショット
            async with db.execute(
                "SELECT * FROM spending_snapshots WHERE snapshot_date = ?",
                (snapshot_date,)
            ) as cursor:
                spending_snapshots = await cursor.fetchall()

            return {
                'date': snapshot_date,
                'assets': dict(asset_snapshot) if asset_snapshot else None,
                'accounts': [dict(row) for row in account_snapshots],
                'spending': [dict(row) for row in spending_snapshots]
            }

    async def get_snapshots_range(
        self,
        start_date: date,
        end_date: date
    ) -> List[Dict[str, Any]]:
        """日付範囲のスナップショットを取得"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row

            async with db.execute("""
                SELECT * FROM daily_asset_snapshots
                WHERE snapshot_date BETWEEN ? AND ?
                ORDER BY snapshot_date
            """, (start_date, end_date)) as cursor:
                snapshots = await cursor.fetchall()
                return [dict(row) for row in snapshots]

    async def update_snapshot_metadata(
        self,
        snapshot_date: date,
        status: str,
        data_source: str = 'scraping',
        error_message: str = None
    ):
        """スナップショットメタデータを更新"""
        async with aiosqlite.connect(self.db_path) as db:
            now = datetime.now()
            completed_at = now if status == 'completed' else None

            await db.execute("""
                INSERT OR REPLACE INTO snapshot_metadata
                (snapshot_date, status, data_source, error_message, started_at, completed_at)
                VALUES (?, ?, ?, ?, COALESCE((SELECT started_at FROM snapshot_metadata WHERE snapshot_date = ?), ?), ?)
            """, (snapshot_date, status, data_source, error_message, snapshot_date, now, completed_at))
            await db.commit()

# 使用例
async def example_usage():
    manager = DailySnapshotManager("moneyforward.db")
    await manager.initialize()

    today = date.today()

    # スナップショット開始を記録
    await manager.update_snapshot_metadata(today, 'pending', 'scraping')

    try:
        # 資産スナップショットを保存
        await manager.save_daily_snapshot(
            snapshot_date=today,
            total_assets=5000000,
            total_liabilities=1000000,
            net_worth=4000000
        )

        # 口座スナップショットを保存
        accounts = [
            {'id': 'acc001', 'name': '三菱UFJ銀行', 'type': 'bank', 'balance': 500000},
            {'id': 'acc002', 'name': '楽天カード', 'type': 'credit_card', 'balance': -50000},
        ]
        await manager.save_account_snapshots(today, accounts)

        # 支出スナップショットを保存
        spending = {
            '食費': {'amount': 50000, 'count': 30},
            '交通費': {'amount': 20000, 'count': 15},
        }
        await manager.save_spending_snapshot(today, spending)

        # スナップショット完了を記録
        await manager.update_snapshot_metadata(today, 'completed', 'scraping')

    except Exception as e:
        await manager.update_snapshot_metadata(today, 'failed', 'scraping', str(e))
        raise

    # スナップショット取得
    snapshot = await manager.get_snapshot_for_date(today)
    print(snapshot)
```

#### 4.3.3 パフォーマンス最適化

```python
class OptimizedSnapshotManager(DailySnapshotManager):
    async def save_complete_snapshot(
        self,
        snapshot_date: date,
        asset_data: Dict[str, int],
        accounts: List[Dict[str, Any]],
        spending: Dict[str, Dict[str, int]]
    ):
        """完全なスナップショットを一括トランザクションで保存"""
        async with aiosqlite.connect(self.db_path) as db:
            # トランザクション開始
            await db.execute("BEGIN TRANSACTION")

            try:
                # メタデータ更新
                await db.execute("""
                    INSERT OR REPLACE INTO snapshot_metadata
                    (snapshot_date, status, data_source, started_at)
                    VALUES (?, 'pending', 'scraping', ?)
                """, (snapshot_date, datetime.now()))

                # 資産スナップショット
                await db.execute("""
                    INSERT OR REPLACE INTO daily_asset_snapshots
                    (snapshot_date, total_assets, total_liabilities, net_worth, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    snapshot_date,
                    asset_data['total_assets'],
                    asset_data['total_liabilities'],
                    asset_data['net_worth'],
                    datetime.now()
                ))

                # 口座スナップショット（一括挿入）
                await db.executemany("""
                    INSERT OR REPLACE INTO account_snapshots
                    (snapshot_date, account_id, account_name, account_type, balance, currency)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, [
                    (
                        snapshot_date,
                        acc['id'],
                        acc['name'],
                        acc['type'],
                        acc['balance'],
                        acc.get('currency', 'JPY')
                    )
                    for acc in accounts
                ])

                # 支出スナップショット（一括挿入）
                await db.executemany("""
                    INSERT OR REPLACE INTO spending_snapshots
                    (snapshot_date, category, amount, transaction_count)
                    VALUES (?, ?, ?, ?)
                """, [
                    (snapshot_date, category, data['amount'], data['count'])
                    for category, data in spending.items()
                ])

                # メタデータ完了
                await db.execute("""
                    UPDATE snapshot_metadata
                    SET status = 'completed', completed_at = ?
                    WHERE snapshot_date = ?
                """, (datetime.now(), snapshot_date))

                # コミット
                await db.commit()

            except Exception as e:
                # ロールバック
                await db.execute("ROLLBACK")

                # エラーを記録
                await db.execute("""
                    UPDATE snapshot_metadata
                    SET status = 'failed', error_message = ?
                    WHERE snapshot_date = ?
                """, (str(e), snapshot_date))
                await db.commit()

                raise
```

### 4.4 長期接続のパフォーマンス考慮事項

長期間接続を保持すると、SQLite のメモリ内ページキャッシュが「ホット」な状態を維持します:

- 頻繁にリクエストされるデータがメモリから直接提供される
- 繰り返しのクエリが高速化される
- I/O 操作が削減される

```python
class ConnectionPool:
    def __init__(self, db_path: str, pool_size: int = 5):
        self.db_path = db_path
        self.pool_size = pool_size
        self._connections = []

    async def get_connection(self):
        if not self._connections:
            return await aiosqlite.connect(self.db_path)
        return self._connections.pop()

    async def return_connection(self, conn):
        if len(self._connections) < self.pool_size:
            self._connections.append(conn)
        else:
            await conn.close()
```

---

## 5. まとめ

### 5.1 主要技術スタック

| 技術 | 用途 | バージョン |
|------|------|-----------|
| FastMCP | MCP サーバーフレームワーク | 2.x (`<3`) |
| Playwright Python | ブラウザ自動化 | v1.57-1.58 |
| aiosqlite | 非同期 SQLite | 0.22.1+ |
| pyotp | TOTP 生成 | 最新 |

### 5.2 推奨アーキテクチャ

```
┌─────────────────────────────────────────────┐
│         FastMCP Server (HTTP)               │
│  - Bearer Token 認証                        │
│  - @mcp.tool デコレータでツール公開          │
│  - ToolError によるエラーハンドリング        │
└─────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────┐
│    Playwright Persistent Context            │
│  - user_data_dir でセッション永続化          │
│  - ヘッドレスモード                          │
│  - Docker コンテナで実行                     │
└─────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────┐
│     マネーフォワード ME スクレイピング       │
│  - Email → Password → TOTP (pyotp)          │
│  - 主要ページのデータ取得                    │
└─────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────┐
│        SQLite キャッシュ層                   │
│  - aiosqlite による非同期操作                │
│  - TTL 付きキャッシュ                        │
│  - 日次スナップショット保存                  │
└─────────────────────────────────────────────┘
```

### 5.3 セキュリティ考慮事項

1. **認証情報の管理**
   - 環境変数で管理 (`.env` ファイル)
   - `.gitignore` に追加
   - TOTP シークレットの暗号化を検討

2. **Bearer Token**
   - JWT トークンの使用
   - 適切な有効期限設定
   - HTTPS 通信の必須化

3. **セッションデータ**
   - Playwright の `user_data_dir` をリポジトリから除外
   - 機密情報を含む Cookie の適切な管理

4. **エラーメッセージ**
   - `mask_error_details=True` で内部エラーをマスク
   - ToolError で適切なエラーメッセージを返す

### 5.4 次のステップ

1. **技術選定の確定**: Architect-Plan と協議
2. **プロトタイプ開発**: 各コンポーネントの PoC
3. **統合テスト**: エンドツーエンドのフロー確認
4. **本番デプロイ**: Docker 環境での運用

---

## 6. 参考文献

### FastMCP
- [fastmcp · PyPI](https://pypi.org/project/fastmcp/)
- [GitHub - jlowin/fastmcp](https://github.com/jlowin/fastmcp)
- [Building an MCP Server and Client with FastMCP 2.0 | DataCamp](https://www.datacamp.com/tutorial/building-mcp-server-client-fastmcp)
- [Build MCP Servers in Python with FastMCP - Complete Guide | MCPcat](https://mcpcat.io/guides/building-mcp-server-python-fastmcp/)
- [Bearer Token Authentication - FastMCP](https://gofastmcp.com/clients/auth/bearer)
- [FastMCP Bearer Token Authentication Quick Start | Medium](https://gyliu513.medium.com/fastmcp-bearer-token-authentication-a-technical-deep-dive-c05d0c5087f4)
- [Implementing Authentication in a Remote MCP Server with Python and FastMCP](https://gelembjuk.com/blog/post/authentication-remote-mcp-server-python/)
- [error_handling - FastMCP](https://gofastmcp.com/python-sdk/fastmcp-server-middleware-error_handling)
- [MCP Error Handling: Don't Let Your Tools Fail Silently | Medium](https://medium.com/@sureshddm/mcp-error-handling-dont-let-your-tools-fail-silently-1b5e02fabe4c)

### Playwright Python
- [BrowserType | Playwright Python](https://playwright.dev/python/docs/api/class-browsertype)
- [Use launch_persistent_context in Playwright Python With Examples | LambdaTest](https://www.lambdatest.com/automation-testing-advisor/python/playwright-python-launch_persistent_context)
- [Docker | Playwright Python](https://playwright.dev/python/docs/docker)
- [Using Persistent Context in Playwright for Browser Sessions | Medium](https://medium.com/@anandpak108/using-persistent-context-in-playwright-for-browser-sessions-c639d9a5113d)
- [Mastering Persistent Sessions in Playwright | Medium](https://medium.com/@Gayathri_krish/mastering-persistent-sessions-in-playwright-keep-your-logins-alive-8e4e0fd52751)
- [Using Persistent Context in Playwright | BrowserStack](https://www.browserstack.com/guide/playwright-persistent-context)

### pyotp
- [PyOTP - The Python One-Time Password Library](https://pyauth.github.io/pyotp/)
- [pyotp · PyPI](https://pypi.org/project/pyotp/)
- [Generating Time-Based OTPs with Python and pyotp](https://www.ruianding.com/blog/generating-time-based-otps-with-python-and-pyotp/)
- [GitHub - pyauth/pyotp](https://github.com/pyauth/pyotp)
- [How To Generate OTPs Using PyOTP in Python](https://blog.ashutoshkrris.in/how-to-generate-otps-using-pyotp-in-python)

### aiosqlite
- [aiosqlite · PyPI](https://pypi.org/project/aiosqlite/)
- [aiosqlite: Sqlite for AsyncIO Documentation](https://aiosqlite.omnilib.dev/)
- [GitHub - omnilib/aiosqlite](https://github.com/omnilib/aiosqlite)
- [Top 5 aiosqlite Code Examples | Snyk](https://snyk.io/advisor/python/aiosqlite/example)
- [cachetools Documentation](https://cachetools.readthedocs.io/)
- [GitHub - colingrady/LiteCache](https://github.com/colingrady/LiteCache)

### Money Forward
- [Money Forward, Inc.](https://corp.moneyforward.com/en/)
- [Money Forward, Inc. · GitHub](https://github.com/moneyforward)

---

**調査完了日**: 2026-02-01
**次回更新**: 技術仕様の変更時または重要なアップデート時
