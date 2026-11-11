# PR #3 review notes

This draft adds the complete Dropbox filename inventory (509 source MP4s; 507 candidates after the two required exclusions), offline manifest generation, and a manual local duplicate-prevention ledger. It contains no upload adapter, scheduled workflow, OAuth secret, public scheduling, Instagram support, or Actions execution.

The Dropbox listing was complete and had no duplicate filenames. The inventory is filename-only and does not include Dropbox URLs. Generated title/description metadata remains filename-based and needs human review.

Local state tracks in_flight, uploaded, failed, and reconcile_required statuses. It prevents duplicate reservations made through this ledger, but does not coordinate across machines and cannot detect external YouTube uploads. An uncertain result requires human Studio reconciliation.

The README replacement could not be committed because the GitHub connector update call rejected its required SHA field despite the current blob SHA being read. PR #2 stays open and draft. No file was changed on main.

Before any activation: move Google OAuth consent out of Testing and handle verification/new token issuance (Testing refresh tokens for YouTube scopes expire after 7 days); verify current Actions billing/allowance; account for schedule delays and automatic disabling of public repo schedules after 60 days without repository activity. Keep daily 7:00 PM Asia/Kolkata disabled.

No tests were run, no Actions workflow was executed, and no upload or schedule was run.
