# Xiaohongshu Collection Profile

Slug: `xiaohongshu`

Status: verified v1 target.

## Entry

- Open `https://www.xiaohongshu.com/`.
- Reuse current login state when possible.
- If search or detail access is blocked, follow the semi-automatic login protocol in `docs/codex-collection-guide.md`.

## Search

- Search each requested keyword from the visible site search UI or search-result page.
- Wait for the search-result page to render.
- Do not use collected detail links as a navigation queue.

## Card Loop

Use this loop for each keyword:

1. Read the current visible waterfall snapshot.
2. Filter out non-post cards such as related-search panels.
3. Keep a weak pre-click fingerprint from visible title, author, time, and count to reduce duplicate click attempts.
4. Move the mouse to the card.
5. Simulate a real click on the card or its visible content area.
6. Wait for the SPA detail modal.
7. Extract fields from the detail modal.
8. Save assets.
9. Close the detail modal with ESC or the close button.
10. Continue with the current snapshot.
11. After the snapshot is exhausted, scroll and re-read the DOM.

## Detail Fields

Preferred selectors and meanings:

- Title: `#detail-title` or visible title in `.note-content`.
- Content: `#detail-desc` or visible desc in `.note-content`.
- Time: visible time text inside the note content area.
- Like count: `.like-wrapper .count`.
- Collect count: `.collect-wrapper .count`.
- Comment count: `.chat-wrapper .count`.
- Main media: large `img` elements in `.media-container`, excluding avatars and background search-result cards.

## Assets

- Save main images to `assets/`.
- Use UUID filenames without hyphens.
- `cover_asset_name` is the first saved image.
- `asset_names` is the rest joined by `|`.
- If one image fails to download, keep the row and record `asset_download_failed`.

## Prohibitions

- Do not use JavaScript click to open cards.
- Do not directly visit `/search_result/...` or `/explore/...` detail URLs as the normal card-entry path.
- Do not save Xiaohongshu transient links in the v1 CSV.
- Do not use the card `href` as a stable ID.

## Known Pitfalls

- Search can show a login wall.
- Results are a waterfall with virtual/reused DOM.
- Card links and detail URLs are session-like and unstable.
- Clicking the wrong point can open an image viewer instead of the post detail.
- Count selectors can accidentally read a background card if extraction is not scoped to the detail modal.
- Some notes have empty title or short body.

## Stop Conditions

Stop the keyword when any condition is met:

- Target row count is reached.
- No new valid rows after repeated scroll rounds.
- Login/risk-control challenge cannot be resolved.
- Browser automation connection is unavailable.
