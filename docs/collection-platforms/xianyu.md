# Xianyu Collection Profile

Slug: `xianyu`

Status: probe-only placeholder.

## V1 Probe Goal

Before bulk collection, verify:

- Search entry and keyword submission.
- Login wall behavior.
- Product card structure.
- Real-click product detail entry.
- Product title, description, price, location, seller, visible activity counts, and image extraction.
- Detail close/back behavior.

## Data Mapping

Main CSV:

- `title`: product title.
- `content`: product description or visible summary.
- `published_at`: visible publish/update time if present.
- `like_count`: visible wants/likes if the platform exposes it.
- `collect_count`: visible collection/favorite-like count if present.
- `comment_count`: visible comment/message count if present.
- `cover_asset_name` and `asset_names`: product images.

Platform-specific fields go to `extra.jsonl`:

```json
{"row_index":1,"platform":"xianyu","price":"99","location":"上海","seller":"example"}
```

## Login

Use the shared semi-automatic login protocol. If Xianyu requires Taobao/Alipay authorization, QR confirmation, device verification, or captcha, stop and ask the user.
