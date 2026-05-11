# tokenpatch AUP / ToS Summary (Repository Copy)

This file is a repository-side summary for internal testing and self-hosted/community usage.  
It is not legal advice and does not replace production terms on `tokenpatch.com`.

## Positioning

- Service type: AI coding cost optimizer / hosted executor service.
- Do not describe service as direct token resale of any upstream model provider.
- You may disclose that hosted executor can run on DeepSeek-compatible infrastructure.

## Acceptable Use Baseline

Users must not use tokenpatch services for:

- malware, credential theft, or unauthorized system access
- attacks, vulnerability exploitation, or botnet activity
- sanctions evasion or use by restricted entities/regions
- illegal content generation or unlawful automation

## Billing and Credit Rules (MVP)

- Invite-only beta can use manual top-up by admin operations.
- Insufficient balance must reject task execution.
- Credits are charged by measured usage and configured pricing rules.
- Operator actions on balances should be auditable (`operator`, `reason`, `before/after`, `request_id`).

## Privacy and Data Handling

- Hosted executor may receive task snippets, diffs, and validation metadata needed to run bounded coding tasks.
- Default logs should minimize stored source content and prioritize metadata, billing, and policy events.
- Provider-side “data for training/optimization” should be disabled where supported for enterprise deployments.

## Risk Controls

- Per-task token caps and payload size limits
- Daily/monthly quota limits
- Freeze-on-anomaly policy switch
- Country/entity restriction checks
