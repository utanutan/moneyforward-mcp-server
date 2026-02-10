# MoneyForward ME 手入力口座の操作知見

## ページ構造

- 口座一覧: `https://moneyforward.com/accounts`
- 手入力口座の個別ページ: `/accounts/show_manual/{hash_id}` (ハッシュIDは口座毎に固有)
- `/accounts/show_manual` 単体はページとして存在しない（404になる）

## 口座URLの取得方法

`/accounts` ページで `a[href*="/accounts/show_manual/"]` のリンクテキストから口座名をマッチさせてURLを取得する。

## 資産の登録・更新パターン

### 初回（資産エントリなし）

1. `#modal_asset_new` をjQueryで `modal("show")` して開く
2. `user_asset_det[asset_subclass_id]` でカテゴリ選択（外貨預金=3）
3. `user_asset_det[name]` に資産名入力
4. `user_asset_det[value]` に金額入力
5. `input[type="submit"]` でフォーム送信
6. POST先: `/bs/portfolio/new`

### 2回目以降（既存エントリあり）

1. `a.btn-asset-action:not([data-method="delete"])` （変更ボタン）をクリック
2. 対応する編集モーダル (`#modal_asset{hash}`) が開く
3. `.modal.in input[name="user_asset_det[value]"]` で金額更新
4. submit

### 既存エントリの判定

`a.btn-asset-action:not([data-method="delete"])` の存在で判定する。`.heading-radius-box` セレクタは口座詳細ページでは存在しない。

## 残高修正 (rollover) フォーム

- `#modal_rollover` にフォームがあるが、資産エントリが0件の場合は「不明なエラーが発生しました」になる
- 資産エントリがある場合でもrolloverは新規残高を上書きする方式のため、変更モーダル経由が確実

## 為替レートAPI

- `https://open.er-api.com/v6/latest/{currency}` で無料取得可能
- レスポンス: `{"result": "success", "rates": {"JPY": 39.78, ...}}`
- httpx の AsyncClient で非同期呼び出し

## セレクタのBootstrap依存

MoneyForward MEはBootstrap 2-3系のモーダルを使用。jQuery `$().modal("show")` でモーダルを直接開ける。開いた状態のモーダルには `.modal.in` クラスが付く。
