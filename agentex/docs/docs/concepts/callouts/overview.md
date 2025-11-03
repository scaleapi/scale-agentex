# Critical Concepts

This section covers critical implementation details that require special attention when working with Agentex. These are the "gotchas" and important nuances that can significantly impact your agent development.

!!! warning "Read These Carefully"
    The concepts in this section are frequently misunderstood or overlooked, leading to production issues. Understanding these will save you from common bugs and race conditions.

## Critical Implementation Details

### [Streaming Accumulation](streaming.md)
**Critical for streaming implementations** - How delta objects are accumulated into final messages and why this matters for client-side streaming.

### [Async Race Conditions](race_conditions.md)
**Critical for production systems** - Why Base ACP has race conditions that corrupt agent state, and how Temporal ACP eliminates them entirely.

### [TaskMessages vs LLM Messages](message_handling.md)  
**Critical for LLM integrations** - The important distinction between Agentex TaskMessages and LLM-compatible message formats, and when conversion is needed.

### [Events vs Messages](events_vs_messages.md)
**Critical for Agentic ACP** - Understanding that events are ephemeral notifications, not persistent objects like TaskMessages.

### [Task/Agent Scoped State](state_management.md)
**Critical for multi-agent systems** - How state is scoped per (task_id, agent_id) and why this design enables parallel agent execution.

---

!!! tip "Implementation Priority"
    If you're just getting started, focus on **TaskMessages vs LLM Messages** and **Streaming** first. These are the most common sources of confusion for new developers.
    
    For production systems, **Race Conditions** is essential reading - it explains why you should use Temporal ACP instead of Base ACP. 