# Developing Agentex Agents

**Choose the right approach for your agent based on your requirements and complexity needs.**

## Three Approaches to Building Agents

Agentex offers three distinct approaches, each designed for different levels of complexity and requirements:

| Approach | Best For | Complexity | Key Features |
|----------|----------|------------|--------------|
| **🚀 Sync Agents** | Chat bots, FAQ systems, quick demos | ~30 lines, 1 file | Immediate responses, auto-scaling, streaming built-in |
| **💪 Agentic Agents** | Customer support, personalized experiences | ~80 lines, 1 file | Persistent memory, multi-turn conversations, event-driven |
| **⚡ Temporal Agents** | Mission-critical systems, complex workflows | 150+ lines, 4 files | Survives restarts, enterprise reliability, distributed execution |

### 🚀 Sync Agents - Simple Request-Response

- **Perfect when you need**: Direct question-answer patterns, stateless processing, minimal complexity
- **What you get**: One handler method (`@acp.on_message_send`), automatic task lifecycle, immediate responses
- **Example use cases**: Customer support chatbots, translation services, data lookups
- **👉 Learn more**: [Agent-to-Client Protocol (ACP)](acp/overview.md) | [Tutorials](tutorials.md)

---

### 💪 Agentic Agents - Stateful Workflows  

- **Perfect when you need**: Persistent memory, multi-step processes, event-driven logic
- **What you get**: Three handler methods, manual message creation, full state control, MongoDB persistence
- **Example use cases**: Multi-step data analysis, interactive applications with memory, complex business processes
- **⚠️ Key difference**: You must manually create all messages using `adk.messages.create()`
- **👉 Learn more**: [Agent-to-Client Protocol (ACP)](acp/overview.md) | [Tutorials](tutorials.md)

---

### ⚡ Temporal Agents - Enterprise Reliability

- **Perfect when you need**: Enterprise reliability, complex state machines, multi-day workflows
- **What you get**: Durable execution, survives server restarts, distributed workflows, complex orchestration
- **Requires**: Temporal workflow knowledge, multiple files, worker configuration
- **👉 Learn more**: [Temporal Guide](temporal-guide.md) | [Tutorials](tutorials.md)

---

## Decision Framework

### Start Here: What Do You Need?

**✅ Choose Sync if**:
- Simple chat interactions
- Stateless processing  
- Quick responses only
- Minimal development time
- Traditional Q&A patterns

**✅ Choose Agentic if**:
- Need to remember conversations
- Multi-step workflows
- Custom state management
- Event-driven processing
- Complex business logic

**✅ Choose Temporal if**:
- Enterprise reliability requirements
- Workflows that must survive restarts
- Multi-day/week processes
- Distributed system coordination
- Mission-critical applications

### When to Upgrade

| Current Situation | Upgrade To | Reason |
|-------------------|------------|---------|
| "I wish my agent remembered what users said earlier" | **Sync → Agentic** | Need persistent state |
| "My agent lost all state when the server restarted" | **Agentic → Temporal** | Need durable execution |
| "I need workflows that run for days/weeks" | **Agentic → Temporal** | Need enterprise reliability |
| "I need to coordinate multiple systems" | **Agentic → Temporal** | Need distributed workflows |

### Warning Signs You Need to Upgrade

- **🟢 → 🟡**: "I wish my agent remembered previous interactions"
- **🟡 → 🔴**: "My agent crashes and loses everything"  
- **🟡 → 🔴**: "I need workflows that survive server restarts"
- **🟡 → 🔴**: "My processes run for hours/days and can't fail"

---

## Migration Paths

When you outgrow your current approach, Agentex provides clear upgrade paths:

### Sync → Agentic Migration
**What changes**: Add state management, implement three handlers instead of one, manually create messages

**👉 Detailed guide**: [Migration Guide](concepts/migration_guide.md#sync-to-agentic)

### Agentic → Temporal Migration  
**What changes**: Convert handlers to Temporal workflows, add worker processes, implement durable execution patterns

**👉 Detailed guide**: [Migration Guide](concepts/migration_guide.md#agentic-to-temporal)

---

## Implementation Guidelines

### Development Workflow

1. **Start Simple**: Begin with Sync unless you know you need complexity
2. **Prototype Fast**: Use Sync to validate your agent logic quickly  
3. **Add Complexity**: Upgrade to Agentic when you need state or workflows
4. **Go Enterprise**: Move to Temporal for production reliability

### Rule of Thumb

**Most developers should stop at Agentic.** Only proceed to Temporal if you need:
- Enterprise-grade reliability
- Multi-day workflows  
- Guaranteed execution despite failures
- Complex distributed coordination

---

## Next Steps

### Ready to Build?

1. **Choose your approach** using the decision framework above
2. **Read the concepts** for your chosen approach:
   - [Agent-to-Client Protocol (ACP)](acp/overview.md) - Covers Sync and Agentic ACP
   - [Temporal Guide](temporal-guide.md)
3. **Set up your environment** with the [Quick Start Guide on GitHub](https://github.com/scaleapi/scale-agentex#quick-start)
4. **Follow the tutorials** to see it in action
5. **Create your agent** with `agentex init`

### Need Help Deciding?

- **Browse tutorials** to see different approaches in action
- **Read the concepts** to understand technical differences
- **Check out critical concepts** for important considerations: [Critical Concepts](concepts/callouts/overview.md)

---

**Remember**: You can always start simple and upgrade later. Agentex is designed to grow with your needs. 