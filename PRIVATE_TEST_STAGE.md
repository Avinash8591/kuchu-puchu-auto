# Private YouTube test stage

This stage adds a manually dispatched, one-file Dropbox download and YouTube upload path. It contains no `schedule` trigger and no Instagram support. The upload adapter fixes YouTube visibility to `private`; it has no visibility or publish-time input. Every run requires the exact `UPLOAD_PRIVATE_TEST` confirmation and human-entered title and description.

## Metadata and prior uploads

The filename is an identifier only. Numeric-only titles are rejected; the workflow does not create a title or description from a numeric filename. Review both fields against the actual video before a test. The uploader checks for an exact title on the authenticated channel before upload; a match blocks the operation for manual reconciliation. The two already handled filenames in PR #3 remain excluded.

## Shared queue state

`queue-state/state.json` on the default branch is the durable ledger. An item is reserved before upload and recorded as uploaded only after YouTube returns a video ID. Failed/uncertain paths remain blocked and require YouTube Studio review. Writes use the previously fetched blob SHA; conflicting writes fail closed. The manual workflow is serialized using GitHub Actions concurrency with queued runs. The workflow token needs repository Contents write permission for this state file. The new file is created on the first private test run.

This design prevents two workflow runs in this repository from claiming the same filename at the same time. It cannot detect an upload performed outside this workflow except for the exact-title lookup, and that lookup is not a substitute for checking YouTube Studio.

## Existing secrets

Keep these existing GitHub Actions secrets unchanged: `DROPBOX_APP_KEY`, `DROPBOX_REFRESH_TOKEN`, `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, `YOUTUBE_REFRESH_TOKEN`. The workflow checks only that they are present and never prints values. Do not paste token values into issues, logs, or source files.

## Before first run

1. Review this draft and its workflow. PR workflows can access repository secrets depending on event/repository settings; do not run untrusted revisions.
2. Confirm the configured OAuth consent-screen publishing status in Google Cloud Console. If it remains External + Testing, Google refresh tokens for YouTube scopes expire after 7 days. The current console state cannot be read from repository access, so the expiry date/status is not independently verified here.
3. Check the GitHub account's Actions billing/usage settings. This repository is public, and standard GitHub-hosted runner minutes are currently free for public repositories; larger runners and storage can incur charges. Account usage and configured spending limits remain account-specific and were not accessible from this repository review.
4. Merge only after review. `workflow_dispatch` is only runnable when the workflow exists on the repository's default branch. Merging this PR does not run an upload. A separate future manual dispatch with an exact confirmation and reviewed metadata is needed to upload a private test.
5. Inspect the resulting video in YouTube Studio and verify it is private. There is no public/unlisted choice and no publish scheduling in this stage.

No scheduled workflow is added or enabled, no Actions workflow was run, no upload was initiated, and no public publishing is present. A separate explicit approval is required for any public or scheduled publishing stage.
