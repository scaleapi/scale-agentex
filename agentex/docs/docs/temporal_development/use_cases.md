# Agent Development with Temporal

Understanding when Temporal becomes essential—and when it's not necessary—helps you choose the right architecture. Here are six scenarios progressing from simple to complex, showing when you don't need Temporal and when it becomes critical:

## 1. Simple Tools

**Scenario:** Basic agent with a simple web search tool. User asks a question, agent uses the tool, returns result.

```mermaid
flowchart LR
    subgraph Interaction["User Interaction"]
        direction TB
        User([User])
        Agent[Agent]

        User <--> Agent
    end

    subgraph Processing["Agent Processing"]
        direction TB
        Tool[Tool: Web Search]
    end

    Agent --> Tool

    style User fill:#e1f5ff
    style Agent fill:#d4edda
    style Tool fill:#fff3cd
```

**Code Example:**
```python
from agents import Agent, Runner, WebSearchTool

agent = Agent(
    name="Assistant",
    tools=[
        WebSearchTool(),
    ],
)

result = await Runner.run(
    agent,
    "Which coffee shop should I go to, taking into account my preferences and the weather today in SF?"
)
print(result.final_output)
```

**Why Temporal is NOT needed:** For simple single-step tools, **Temporal is not necessary**. Base Agentic ACP or even Sync ACP is sufficient for basic operations that complete quickly and don't require durability. Use Base ACP without Temporal for these cases—it's simpler, faster to develop, and has less operational overhead. Temporal only becomes essential when you need the capabilities shown in the scenarios below.

---

## 2. Durability: Complex Multi-Step Tools

**Scenario:** Invoice processing with multiple sequential steps: Download File → Extract Info → Validate Info → Initiate Payment

```mermaid
graph LR
    User([User])
    Agent[Agent]
    Tool[Tool: Process<br/>Invoice]

    subgraph ToolSteps["Tool Execution Steps"]
        Step1[Download File]
        Step2[Extract Info]
        Step3[Validate Info]
        Step4[Initiate Payment]
    end

    User --> Agent
    Agent --> Tool
    Tool --> Step1
    Step1 --> Step2
    Step2 --> Step3
    Step3 --> Step4

    style User fill:#e1f5ff
    style Agent fill:#d4edda
    style Tool fill:#fff3cd
    style Step1 fill:#f8d7da
    style Step2 fill:#f8d7da
    style Step3 fill:#f8d7da
    style Step4 fill:#f8d7da
```

**Code Example:**
```python
@function_tool
def process_invoice(file_uri: str) -> str:
    file = workflow.execute_activity(download_file, file_uri)
    vendor_info = workflow.execute_activity(extract, file)
    valid = workflow.execute_activity(validate, vendor_info)
    if valid:
        workflow.execute_activity(pay, vendor_info.vendor)
        return f"Success: payment sent to {vendor_info.vendor}"
    else:
        return "Failure: invalid invoice."
```

**Why Temporal is needed:** Without Temporal, if the "extract" step fails, you'd have to re-download the file. If "validate" fails, you'd have to re-download AND re-extract. **Temporal persists state after each `execute_activity` call**, so failures only retry the failed step. This is critical for expensive operations (file downloads, API calls, payments) where you can't afford to redo work. Temporal also provides automatic retries with backoff policies for transient failures.

---

## 3. Composability: Human-in-the-Loop

**Scenario:** Invoice processing that requires human approval before proceeding with the full workflow.

```mermaid
flowchart LR
    subgraph Interaction["User Interaction"]
        direction TB
        User([User])
        Agent[Agent]
        Tool[Tool: Process<br/>Invoice]

        User <--> Agent
        Agent --> Tool
    end

    subgraph WorkflowSteps["Approval Workflow"]
        direction TB
        Approval[Human Approval]
        Step1[Download File]
        Step2[Extract Info]
        Step3[Validate Info]
        Step4[Initiate Payment]

        Approval --> Step1
        Step1 --> Step2
        Step2 --> Step3
        Step3 --> Step4
    end

    Tool --> Approval

    style User fill:#e1f5ff
    style Agent fill:#d4edda
    style Tool fill:#fff3cd
    style Approval fill:#ffeaa7
    style Step1 fill:#f8d7da
    style Step2 fill:#f8d7da
    style Step3 fill:#f8d7da
    style Step4 fill:#f8d7da
```

**Code Example:**
```python
@function_tool
async def process_invoice(file_uri: str) -> str:
    return await workflow.execute_child_workflow(...)

@workflow.defn
class ApproveAndProcessInvoiceWorkflow:
    def __init__(self, approved: bool = False):
        self._approved = approved

    @workflow.signal
    async def on_approval(self, event: ApprovalEvent) -> None:
        self._approved = event.approved

    @workflow.run
    async def run(self, file_uri: str) -> str:
        # re-evaluated when approval signal arrives
        await workflow.wait_condition(lambda: self._approved)
        if self._approved:
            # download, extract, validate, and pay (if valid)
        else:
            return "Failure: invalid invoice."
```

**Why Temporal is needed:** The agent needs to wait for human approval, which could take minutes, hours, or days. **Temporal workflows can pause indefinitely using `wait_condition()` without consuming active resources.** When the human approves (via a signal), the workflow wakes up and continues exactly where it left off. Without Temporal, you'd need to build a complex state machine with polling or webhooks to track where each workflow paused and resume it later. Temporal handles all of this automatically through durable execution and signals.

---

## 4. Autonomous Execution: Scheduled Wake-ups

**Scenario:** Agent schedules a future check (e.g., "check for invoice comments in 3 days"), sleeps, then wakes itself up to continue work.

```mermaid
flowchart LR
    subgraph Interaction["User Interaction"]
        direction TB
        User([User])
        Agent[Agent]
        Tool[Tool: Schedule<br/>for later]

        User <--> Agent
        Agent --> Tool
    end

    subgraph DelayedWorkflow["Delayed Child Workflow"]
        direction TB
        Wait[Wait delay secs]
        Ping[Ping OG agent]
        Wake[Agent wakes up]

        Wait --> Ping
        Ping --> Wake
    end

    Tool --> Wait
    Wake -.-> Agent

    style User fill:#e1f5ff
    style Agent fill:#d4edda
    style Tool fill:#fff3cd
    style Wait fill:#ffeaa7
    style Ping fill:#f8d7da
    style Wake fill:#d4edda
```

**Code Example:**
```python
@function_tool
async def check_for_comments(invoice_id: str, delay: int) -> str:
    return await workflow.start_child_workflow(
        DelayedWorkflow, prompt, start_delay=delay
    )

@workflow.defn
class DelayedWorkflow:
    @workflow.run
    async def run(self, invoice_id: str) -> str:
        handle = workflow.get_external_workflow_handle_for(AgentWorkflow)
        await handle.signal(
            AgentWorkflow.on_event,
            Event(prompt=f"Resolve comments for invoice: {invoice_id}")
        )

@workflow.defn
class AgentWorkflow:
    @workflow.signal
    async def on_event(self, event: Event) -> None:
        # Add event.prompt to Agent inputs and move forwards
```

**Why Temporal is needed:** Agents need to schedule future actions without polling. **Temporal child workflows can sleep for arbitrary durations (seconds, days, weeks) using `start_delay`, then signal parent workflows to wake them up.** This enables "check back later" patterns without maintaining active connections or cron jobs. Without Temporal, you'd need external scheduling systems, polling mechanisms, or complex timer infrastructure. Temporal makes time-based orchestration a first-class primitive.

---

## 5. Queueing: Async Batch Processing

**Scenario:** Agent receives events from multiple sources (webhooks, users, schedules) and processes them in batches rather than one-by-one.

```mermaid
flowchart LR
    subgraph EventSources["Event Sources"]
        direction TB
        Sources[Webhooks<br/>Users<br/>Schedules]
        Event1[1]
        Event2[2]
        Event3[3]
        Event4[4]

        Sources --> Event1
        Sources --> Event2
        Sources --> Event3
        Sources --> Event4
    end

    subgraph AgentProcessing["Agent Processing"]
        direction TB
        Queue[Queue: Events]
        Process[Process Batch]

        Queue --> Process
    end

    Event1 --> Queue
    Event2 --> Queue
    Event3 --> Queue
    Event4 --> Queue

    style Sources fill:#e1f5ff
    style Event1 fill:#fff3cd
    style Event2 fill:#fff3cd
    style Event3 fill:#fff3cd
    style Event4 fill:#fff3cd
    style Queue fill:#ffeaa7
    style Process fill:#d4edda
```

**Code Example:**
```python
@workflow.defn
class AgentWorkflow:
    @workflow.init
    def __init__(self, TaskParams):
        self._queue: asyncio.Queue[Event] = asyncio.Queue()
        self._batch_size = BATCH_SIZE

    @workflow.signal
    async def on_event(self, event: Event) -> None:
        self._queue.put(event)

    @workflow.run
    async def run(params: TaskParams):
        # process events as they come in
        while True:
            await workflow.wait_condition(
                lambda: self._queue.qsize() >= self._batch_size,
            )
            current_batch = dequeue_all(self._queue, self._batch_size)
            await workflow.execute_child_workflow(  # blocking
                workflow=ProcessAgentEvents.run,
                args=[current_batch],
            )
```

**Why Temporal is needed:** Processing each event individually is inefficient (API rate limits, batching for analytics, coordinated actions). **Temporal workflows maintain in-memory queues (`asyncio.Queue`) as part of workflow state**, allowing events to accumulate and batch process when thresholds are met. Events received via signals are stored durably in the workflow's event history. Without Temporal, you'd need external queuing systems (Redis, SQS) with complex coordination logic. Temporal makes the queue part of the workflow itself, with automatic persistence and exactly-once processing guarantees.

---

## 6. Long-Running Workflows: Real-World Business Processes

**Scenario:** A 50+ day procurement workflow that wakes and sleeps in response to real-world events:

- **Day 1:** Approve HVAC → Issue PO → Sleep
- **Day 14:** Check tracking → Detect delay → Surface options → Sleep
- **Day 15:** Human cancels → Reorder from alternate → Sleep
- **Day 50:** Windows arrive, steel delayed → Coordinate storage → Sleep

```mermaid
graph TB
    Day1["Day 1:<br/>HVAC Approved"]
    Day14["Day 14:<br/>Check Tracking"]
    Day15["Day 15:<br/>PM Decision"]
    Day50["Day 50:<br/>Windows Arrived"]

    Day1 -.Sleep.-> Day14
    Day14 -.Sleep.-> Day15
    Day15 -.Sleep.-> Day50

    subgraph Run1["Day 1 Agent Run"]
        Event1["Wake"]
        PO1["Issue PO"]
        Track1["Create Tracking"]
        Sleep1["Sleep"]

        Event1 --> PO1
        PO1 --> Track1
        Track1 --> Sleep1
    end

    subgraph Run14["Day 14 Agent Run"]
        Event14["Wake"]
        Query["Query Vendor<br/>System"]
        Delay["Detect 3+ Week<br/>Delay"]
        Options["Surface 3 Options<br/>to PM"]
        Sleep14["Sleep"]

        Event14 --> Query
        Query --> Delay
        Delay --> Options
        Options --> Sleep14
    end

    subgraph Run15["Day 15 Agent Run"]
        Event15["Wake"]
        Cancel["Cancel Old<br/>Order"]
        Reorder["Issue New<br/>Order"]
        Notify["Notify Installation<br/>Crews"]
        Sleep15["Sleep"]

        Event15 --> Cancel
        Cancel --> Reorder
        Reorder --> Notify
        Notify --> Sleep15
    end

    subgraph Run50["Day 50 Agent Run"]
        Event50["Wake"]
        Detect["Materials Out<br/>of Order"]
        Coordinate["Coordinate<br/>Storage"]
        Adjust["Adjust Crew<br/>Schedules"]
        Sleep50["Sleep..."]

        Event50 --> Detect
        Detect --> Coordinate
        Coordinate --> Adjust
        Adjust --> Sleep50
    end

    Day1 --> Event1
    Day14 --> Event14
    Day15 --> Event15
    Day50 --> Event50

    style Day1 fill:#e1f5ff
    style Day14 fill:#e1f5ff
    style Day15 fill:#e1f5ff
    style Day50 fill:#e1f5ff
    style Event1 fill:#d4edda
    style Event14 fill:#d4edda
    style Event15 fill:#d4edda
    style Event50 fill:#d4edda
    style Sleep1 fill:#e7e7ff
    style Sleep14 fill:#e7e7ff
    style Sleep15 fill:#e7e7ff
    style Sleep50 fill:#e7e7ff
    style PO1 fill:#fff3cd
    style Track1 fill:#fff3cd
    style Query fill:#fff3cd
    style Delay fill:#f8d7da
    style Options fill:#fff3cd
    style Cancel fill:#f8d7da
    style Reorder fill:#fff3cd
    style Notify fill:#fff3cd
    style Detect fill:#f8d7da
    style Coordinate fill:#fff3cd
    style Adjust fill:#fff3cd
```

**Why Temporal is needed:** Business processes span arbitrary timeframes (days, weeks, months) with unpredictable events. **Temporal workflows can run indefinitely, waking in response to external signals (webhooks, scheduled checks, human decisions) while maintaining complete state continuity.** The workflow knows it's on Day 50, which vendor was used, what decisions were made on Day 15, and can access the full history. Without Temporal, you'd need to persist all state externally, build resumption logic, handle partial failures, and orchestrate wake-ups manually. Temporal makes long-running, event-driven processes as simple as writing sequential code with signals and wait conditions.

**Key Insight:** Most business-critical processes are long and dynamic. They must adapt to unpredictable, real-world events. Agentex, with its native Temporal integration, gives AI agents the critical capabilities needed to orchestrate complex workflows.
