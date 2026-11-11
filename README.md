# Kuchu Puchu YouTube Queue

Preview-first YouTube queue tooling. Instagram is out of scope for this stage.

## Safety status

This branch contains an offline preview planner only. There is no upload adapter or scheduled workflow. Do not add credentials or video URLs to git. No upload or schedule was run while preparing this branch.

## Queue rules

- Source: Dropbox folder `/kuchu puchu tap karo_` (a Dropbox listing/download adapter remains to be configured).
- Stable order: numeric filename prefix, then full filename as a deterministic tie breaker; non-numeric MP4 names sort after numeric names.
- Excluded: `001.mp4` (already scheduled) and `3932954021832974372.mp4` (private test upload succeeded).
- The preview planner consumes a text listing and emits deterministic pending items. State persistence, content hashing, and YouTube reconciliation must be added before any upload implementation; intentionally absent here.
- Metadata uses a child-friendly template derived from the filename. It does not inspect video contents, so a human must review all metadata.

## Preview

`python -m queue_scheduler preview --files-list examples/files.txt --output work/manifest.json`

The example listing is synthetic and offline. It is not the actual Dropbox listing and contains no upload logic.

## Activation requirements

1. Generate and review the complete manifest against Dropbox and YouTube Studio, including any other previously scheduled or published files.
2. Provide least-privilege Dropbox access for listing/downloading, stored only as an Actions secret.
3. Resolve OAuth consent status. External Google OAuth apps left in Testing issue refresh tokens that expire after 7 days for YouTube scopes. Unattended use requires moving the consent app out of Testing, completing applicable verification, then issuing and securely storing a replacement offline refresh token. Otherwise expect periodic human reauthorization.
4. Check the account's current Actions allowance/billing before activation. Public-repo scheduled workflows can be automatically disabled after 60 days without repository activity; runs can also be delayed or dropped during high GitHub load. This cannot guarantee upload at exactly 19:00 IST.
5. Verify YouTube API project eligibility. Uploads from unverified API projects may be restricted to private viewing. YouTube scheduling uses a future `publishAt` on a never-published private video; past times can make it public immediately. Failures with uncertain upload outcome must be reconciled before retrying.
6. After separate design and manifest review, add a disabled-by-default manual upload workflow requiring an exact confirmation phrase; add a recurring 19:00 Asia/Kolkata schedule only after separate explicit activation approval.

The next approval needed is review of the real manifest and queue design. Public scheduling and activation require separate explicit approval. This branch contains neither.