# Douyin Collection Profile

Slug: `douyin`

Status: probe-only placeholder.

## V1 Probe Goal

Before bulk collection, verify:

- Search entry and keyword submission.
- Whether login is required for search results.
- Whether a video card can be opened with real click interaction.
- How to read title, author, visible time, like count, comment count, and cover image.
- Whether video download is allowed and stable. V1 defaults to cover/metadata only.

## V1 Boundary

- Do not bulk collect Douyin until the card-entry, detail-read, asset-extraction, close, and scroll loop is verified.
- Do not download video bodies by default.
- Save platform-specific fields such as duration or music title to `extra.jsonl` when they become available.

## Login

Use the shared semi-automatic login protocol. If Douyin shows QR-only, captcha, device verification, or risk-control prompts, stop and ask the user.
