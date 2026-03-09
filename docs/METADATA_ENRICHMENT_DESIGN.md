# Metadata Enrichment Design

**Status:** PENDING DESIGN — awaiting user input
**Created:** March 9, 2026
**Owner:** TBD

---

## What Is Metadata Enrichment?

> **OPEN QUESTION:** The audit identified "metadata enrichment" as a planned feature
> with no design or implementation. The following is a placeholder based on the
> project's known goals. Please review and confirm/correct before implementation.

**Working definition:** Metadata enrichment is the process of augmenting file records
in `manifest.db` with additional computed or sourced fields beyond what the scanner
captures, to enable more accurate duplicate detection and smarter cleanup decisions.

---

## Proposed Enrichment Fields

| Field | Source | Description | Priority |
|-------|--------|-------------|----------|
| `content_hash` | Computed | SHA-256 of file content (vs filename-based match) | HIGH |
| `perceptual_hash` | Computed | pHash for image deduplication | MEDIUM |
| `exif_datetime` | EXIF metadata | True capture date for photos | HIGH |
| `camera_model` | EXIF metadata | Camera used (affects which copy to keep) | LOW |
| `location_name` | Reverse geocode | Human-readable location from GPS coords | LOW |
| `album_memberships` | Google Photos API | Which albums contain this photo | MEDIUM |
| `cloud_last_modified` | Drive API | Server-side modified timestamp | MEDIUM |
| `is_shared` | Drive API | Whether file is shared with others | HIGH |
| `download_count` | Drive API | Usage signal for retention decisions | LOW |

---

## Proposed Architecture

```
manifest.db (existing)
    ↓
enricher.py (NEW — to be created)
    ↓
manifest.db (updated with enriched fields)
    ↓
classifier.py (uses enriched fields for better deduplication)
```

**File:** `tools/enricher.py` — NOT YET CREATED
**Schema changes:** New columns in `manifest.db` `files` table — NOT YET DESIGNED

---

## Open Questions for User

1. **Scope:** Should enrichment apply to all files or only photos/videos?
2. **Content hashing:** Files >1GB will be slow — use quick_xor or full SHA-256?
3. **Perceptual hashing:** Requires Pillow or pHash library — acceptable dependency?
4. **Google Photos albums:** Requires additional API scope — acceptable?
5. **When does enrichment run?** After scanner (Phase 1), before classifier (Phase 2)?
6. **Incremental enrichment:** Re-enrich only new files or all files?

---

## Next Steps (BLOCKED on design approval)

- [ ] User confirms/refines scope above
- [ ] Schema design for new `manifest.db` columns
- [ ] Create `tools/enricher.py`
- [ ] Update `phase2/classifier.py` to use enriched fields
- [ ] Add enrichment tests

**Status: PENDING USER REVIEW**
