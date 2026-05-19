# Safe Refactor Skill

Read AGENTS.md first.

Goal:
Apply incremental low-risk refactors.

Requirements:
- preserve Telegram UX
- preserve handler wiring
- preserve callback paths
- avoid rewriting stable modules
- avoid large architectural rewrites
- minimize side effects
- preserve backward compatibility

Before changes:
- inspect imports
- inspect call paths
- inspect runtime dependencies

After changes:
- run compile validation
- inspect broken imports
- inspect callback registration
- inspect runtime risks

Always summarize:
- exact files changed
- exact behavior changed
- remaining risks
- unverified assumptions