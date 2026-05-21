# tokenpatch Acceptable Use Summary

This repository includes a short, non-legal summary of the intended acceptable
use baseline for the open-source client and any hosted executor service.
Production deployments should use their own full Terms of Service, Privacy
Policy, Acceptable Use Policy, and refund or credit policy.

## Product Positioning

- tokenpatch is an AI coding cost optimizer and bounded executor workflow.
- Hosted executor mode should be described as a structured coding service, not
  direct resale of an upstream model provider's API.
- It is acceptable to disclose that the hosted executor can use
  DeepSeek-compatible infrastructure, without implying official partnership or
  endorsement.

## Prohibited Uses

Users must not use tokenpatch or hosted executor services for:

- malware, credential theft, or unauthorized system access
- attacks, vulnerability exploitation, botnet activity, or evasion tooling
- sanctions evasion or use by restricted entities or regions
- illegal content generation or unlawful automation
- attempts to bypass task, token, file, or rate limits

## Credits and Usage

- Insufficient balance should reject hosted executor task execution.
- Credits should be charged by measured usage and configured pricing rules.
- Balance changes should be auditable with operator, reason, before/after
  balance, timestamp, and request identifier.

## Privacy and Data Handling

- Hosted executor mode may receive task snippets, diffs, and validation metadata
  needed to run bounded coding tasks.
- Default logs should minimize stored source content and prioritize task
  metadata, usage, billing, and policy events.
- Provider-side data usage for training or optimization should be disabled where
  supported for enterprise deployments.

## Risk Controls

- Per-task token caps and payload size limits
- Daily/monthly quota limits
- Freeze-on-anomaly policy switch
- Country and entity restriction checks
