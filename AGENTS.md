# AIMA Engineering Rules

## Product
AIMA is an AI-powered Telegram opportunity intelligence assistant.

Core product goals:
- surface REAL opportunities
- avoid noisy ecosystem spam
- prioritize actionable content
- maintain premium UX quality
- avoid stale content
- avoid fake AI behavior

## Stack
- Python
- Telegram Bot API
- Telethon
- SQLite
- OpenRouter / Gemini
- Modular service architecture

## Architecture Rules
- Never break existing Telegram flows.
- Prefer incremental refactors.
- Avoid rewriting working modules.
- Services orchestrate pipeline behavior.
- Telegram bot should remain thin.
- Repository layer owns DB access.
- Do not duplicate business logic.

## UX Rules
- No Telegram link previews.
- Avoid noisy multi-message spam.
- Prefer edit-in-place UX.
- Keep formatting clean and premium.
- Never expose raw exceptions to users.

## Opportunity Rules
Strong opportunities:
- grants
- accelerators
- hackathons
- startup programs
- fellowships
- investor calls
- incubators

Weak content to suppress:
- generic networking
- ticket sales
- ecosystem PR
- ceremonies
- generic meetups
- vague ecosystem news

## Digest Rules
Digest must:
- feel curated
- avoid repetition
- avoid stale opportunities
- prioritize actionable items
- prioritize recency
- prioritize uniqueness

## Performance Rules
User hardware:
- Acer Aspire 3
- i3-7020U
- low-power CPU

Avoid:
- unnecessary full DB scans
- expensive refresh loops
- duplicate pipeline execution
- blocking Telegram handlers

## Development Rules
Before modifying architecture:
1. inspect existing call paths
2. inspect runtime side effects
3. preserve backward compatibility
4. explain risks before large refactors

After changes:
- run compile validation
- inspect imports
- verify Telegram callback paths
- verify no handler breakage
- summarize exact changed behavior

Never pretend functionality works if not verified.