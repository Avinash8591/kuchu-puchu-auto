# Kuchu Puchu Auto Publisher

Cloud automation project for the Kuchu Puchu publishing queue.

## Planned workflow
- Read MP4 files from the configured Dropbox folder in numeric filename order.
- Exclude `001.mp4`, which is already scheduled.
- Generate platform-specific metadata.
- Publish one video daily at 19:00 Asia/Kolkata to YouTube Shorts and Instagram Reels.
- Record publication state to prevent duplicates.

## Safety
This is a scaffold only. No credentials are stored here and no publishing workflow is active. Live publishing will remain disabled until API access is configured and tested, and explicit approval is given.

## Secrets
Never commit passwords, API tokens, OAuth refresh tokens, client secrets, or private video links. Store credentials only in GitHub Actions Secrets.

## Cost notes
A zero-cost deployment is a target, not a guarantee. We must verify runner limits, AI API availability, video delivery/hosting, platform eligibility, and quotas before activation. Instagram needs a fetchable video URL; Dropbox delivery must be tested before selecting an approach.
