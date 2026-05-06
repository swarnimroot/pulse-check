# URL curation — smoke-set (bite 6.2)

Operator fills the **URL** column for each row below. Once filled, paste back / commit and I'll run the scrape + classify + tag + aggregate pipeline end-to-end on the expanded corpus.

## Rules

- **One canonical SKU per (product × marketplace).** Pick the most popular / mid-spec configuration. Don't list multiple variants of the same model.
- **Must be a product page with reviews visible.** BestBuy product page (`/site/.../<SKU>.p`), Amazon product page (`/dp/<ASIN>`). Not a search-result or category page.
- **US storefront preferred** (`bestbuy.com`, `amazon.com`) — scrapers-lib wrappers were tested against US.
- **Leave blank if no good match exists.** Better an empty cell than a wrong SKU. Common case: Alienware sometimes only sells direct on `dell.com` (no Amazon listing) — flag with a note in the URL cell (e.g. `# none on amazon`) and we'll skip that source for that product.

## Checklist

### 1. Alienware 16 Aurora
- **product_id:** `alienware_16_aurora`
- **brand:** Alienware
- **target spec hint:** 2025 model, 16" QHD+ display, RTX 50-series. Pick whichever SKU has the most reviews. Avoid legacy m16 / m18 / x16.

| Marketplace | URL |
|-------------|-----|
| BestBuy     | `<paste URL or "# none">` |
| Amazon      | `<paste URL or "# none">` |

### 2. ROG Strix G16
- **product_id:** `rog_strix_g16`
- **brand:** ASUS ROG
- **target spec hint:** 2024–2025 G16 (NOT G15, NOT SCAR 16). Mid-spec RTX 4060/4070 typical. Highest-review-count SKU.

| Marketplace | URL |
|-------------|-----|
| BestBuy     | `<paste URL or "# none">` |
| Amazon      | `<paste URL or "# none">` |

## What I'll do once URLs are in

1. Patch the URLs into `configs/product_set_smoke_test.yaml` (`urls.bestbuy` / `urls.amazon` slots).
2. Run `scripts/scrape.py --run-config configs/run_smoke_test.yaml` against the new sources (Reddit corpus already in DB; this adds BestBuy + Amazon mentions).
3. Re-run `scripts/classify_content_type.py` on new mentions (Haiku-cached for any duplicates).
4. Re-run `scripts/tag.py` with `--exclude-content-types deal` on the expanded corpus.
5. Re-run A1 aggregation.
6. Report density delta (mentions per product post-filter) + cost.
