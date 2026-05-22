# Weibo Collection Profile

Slug: `weibo`

Status: probe-only placeholder.

## V1 Probe Goal

Before bulk collection, verify:

- Search entry and keyword submission.
- Login wall behavior.
- Feed card structure.
- Real-click or in-feed expansion path.
- How to expand full text.
- Text, author, time, repost count, comment count, like count, and image extraction.

## Data Mapping

Main CSV:

- `title`: short text fallback or topic title when present.
- `content`: full Weibo text after expansion if possible.
- `published_at`: visible time.
- `like_count`: visible like count.
- `collect_count`: leave blank unless a stable collection-like count exists.
- `comment_count`: visible comment count.
- `cover_asset_name` and `asset_names`: visible post images.

Platform-specific fields go to `extra.jsonl`:

```json
{"row_index":1,"platform":"weibo","repost_count":"12","author":"example"}
```

## Login

Use the shared semi-automatic login protocol. If Weibo shows captcha, QR-only, device verification, or risk-control prompts, stop and ask the user.
