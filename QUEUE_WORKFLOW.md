# Kuchu Puchu YouTube Queue

Preview-first YouTube queue tooling. Instagram is out of scope.

## Safety status

This branch adds a Dropbox-derived filename inventory, offline preview tooling, and a local state ledger. There is no Dropbox client, YouTube upload client, public scheduling action, or recurring workflow. Nothing here uploads or schedules videos. Never commit credentials, tokens, or private video links.

## Dropbox-derived queue inventory

`examples/dropbox-files.txt` was generated from a complete direct listing of `/kuchu puchu tap karo_` on 2026-11-11. The listing contained 509 MP4 files, no other file types, and no duplicate filenames. The queue has 507 candidates after excluding `001.mp4` and `3932954021832974372.mp4`. The inventory contains filenames only, with no downloadable URLs. Generated titles are filename-based and need human review.

Numeric filename prefixes determine order; case-insensitive filename order breaks ties. Non-numeric names sort after numeric names.

## Offline preview and manual state operations

Preview the queue:

```sh
python -m queue_scheduler.manual preview --files-list examples/dropbox-files.txt --output work/manifest.json
```

Preview reads the local filename list and writes metadata with private visibility as a conservative default. It does not inspect video content or contact Dropbox, YouTube, or any other service.

The state ledger is local and ignored by git. Run state commands only after manually checking YouTube Studio. They only write the JSON ledger and never contact YouTube:

```sh
python -m queue_scheduler.manual reserve --files-list examples/dropbox-files.txt --state work/queue-state.json --filename 3934291883065293059.mp4
python -m queue_scheduler.manual complete --files-list examples/dropbox-files.txt --state work/queue-state.json --filename 3934291883065293059.mp4 --youtube-video-id VIDEO_ID
python -m queue_scheduler.manual fail --files-list examples/dropbox-files.txt --state work/queue-state.json --filename 3934291883065293059.mp4
python -m queue_scheduler.manual reconcile --files-list examples/dropbox-files.txt --state work/queue-state.json --filename 3934291883065293059.mp4
```

A reservation marks an item `in_flight`; a duplicate reservation is refused. Completion records an uploaded status and video ID. For an uncertain outcome, reconcile YouTube Studio manually before any retry; this local ledger cannot detect uploads made outside it. State transitions require a person to run the command. A future real upload stage requires durable shared state, an atomic claim, and authoritative reconciliation before retries.

## Activation requirements

- Google OAuth apps left in Testing issue refresh tokens that expire after 7 days for YouTube scopes. Unattended use needs production-ready consent configuration, applicable verification, and a newly issued securely stored refresh token. Otherwise human reauthorization is needed.
- GitHub scheduled events can be delayed or dropped under load; public repository schedules may be disabled after 60 days without repository activity. A 7:00 PM Asia/Kolkata run cannot guarantee that exact time.
- Actions allowance and billing depend on account and repository configuration. The current allowance was not available for verification; check it before considering activation.
- Confirm YouTube API project eligibility and privacy/scheduling behavior before any future upload work.
- No daily schedule, upload workflow, public scheduling, Instagram support, or Actions execution is included. A separate explicit approval is required before adding an upload or recurring public schedule.

PR #2 remains a separate preview-only draft. This draft adds the reviewed Dropbox inventory and local manual state workflow for review; it is not approval to merge or publish.
