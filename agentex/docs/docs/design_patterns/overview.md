# Design Patterns

Reusable, battle-tested patterns for building production-grade agents with Agentex.

## What Are Design Patterns?

Design patterns are proven solutions to common problems in agent development. Unlike guides (which teach you how to use a feature), patterns show you how to solve specific architectural challenges.

**Use Guides when:** You're learning a new technology or feature
**Use Design Patterns when:** You have a specific problem to solve

---

## Available Patterns

### OpenAI SDK Integration Patterns

Patterns for building durable agents with the OpenAI Agents SDK and Temporal:

#### [Multi-Activity Tools](multi_activity_tools.md)
**Problem:** Need atomic multi-step operations (e.g., withdraw + deposit for money transfer)
**Solution:** Compose multiple Temporal activities within a single tool call
**Use when:** Operations must complete together or fail together

#### [Human-in-the-Loop](human_in_the_loop.md)
**Problem:** Agents need human approval without losing state
**Solution:** Use Temporal signals and child workflows for approval workflows
**Use when:** High-stakes decisions, compliance requirements, human oversight needed

---

## Pattern Categories

### Integration Patterns
How to integrate external SDKs and frameworks:
- OpenAI Agents SDK (available now)
- MCP Protocol (coming soon)
- LangChain integration (coming soon)

### Workflow Patterns
Common workflow orchestration patterns:
- Multi-activity tools (available now)
- Human-in-the-loop (available now)
- Multi-agent coordination (coming soon)
- Long-running processes (coming soon)

### State Management Patterns
Patterns for managing complex state:
- Task-scoped state (see [State Concepts](../concepts/state.md))
- Cross-agent state sharing (coming soon)

---

## How to Use This Section

1. **Identify your problem** - What challenge are you facing?
2. **Find the pattern** - Browse available patterns above
3. **Study the implementation** - Each pattern includes complete code examples
4. **Adapt to your needs** - Patterns are templates, not prescriptions

---

## Related Guides

Before diving into design patterns, make sure you understand the fundamentals:

- **[OpenAI SDK Integration Guide](../guides/openai_temporal_integration.md)** - Setup and basic usage
- **[Temporal Guide](../temporal-guide.md)** - Essential Temporal concepts
- **[Migration Guide](../concepts/migration_guide.md)** - Upgrading between ACP types

---

## Contributing Patterns

Have a pattern that solved a tough problem? Consider contributing:
1. Document the problem and solution
2. Provide complete working code
3. Include when to use (and when not to use)
4. Add visual diagrams if helpful

---

## Next Steps

- **New to Temporal?** Start with the [Temporal Guide](../temporal-guide.md)
- **Need to set up OpenAI SDK?** See the [OpenAI SDK Integration Guide](../guides/openai_temporal_integration.md)
- **Ready for patterns?** Explore [Multi-Activity Tools](multi_activity_tools.md) or [Human-in-the-Loop](human_in_the_loop.md)
