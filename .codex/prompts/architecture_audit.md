# Architecture Audit Skill

Read AGENTS.md first.

Analyze the project architecture deeply.

Focus on:
- Telegram bot flow
- services orchestration
- repository layer
- pipeline freshness
- stale data behavior
- sync vs async risks
- callback safety
- duplicate logic
- DB bottlenecks
- runtime risks
- UX architecture problems
- scalability risks

Rules:
- do not modify code
- do not rewrite architecture
- do not generate fake improvements
- preserve existing working flows

Output:
1. architecture summary
2. strongest parts
3. weakest parts
4. runtime risks
5. scalability risks
6. performance bottlenecks
7. dangerous abstractions
8. prioritized fix plan