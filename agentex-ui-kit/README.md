# Agentex UI Kit

React component library for building AI agent interfaces.

## Development Setup

### 1. Start Agentex Backend

```bash
# in agentex/agentex
make dev
```

⚠️ If messages aren't streaming after going through dev setup, try running `brew services stop redis` and restarting Agentex Backend. ⚠️

### 2. Register an ACP Agent

```bash
# in agentex-python/examples/tutorials/10_agentic/020_streaming
# or your preferred ACP agent directory

# One-time setup
uv init
uv pip install -r requirements.txt
echo -e "OPENAI_API_KEY=...\nENVIRONMENT=development" > .env

# Register agent (run each time you restart backend)
uv run --env-file=.env agentex agents run --manifest manifest.yaml
```

### 3. Start Development Server

```bash
# in agentex/agentex-ui-kit
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) to see the development app.

⚠️ If messages aren't streaming, try running `brew services stop redis` and restarting Agentex Backend in step 1. ⚠️

## Using Agentex UI Kit in Your Project

Components are distributed using the [shadcn/ui](https://ui.shadcn.com) pattern.

### 1. Setup shadcn/ui in your project

[ui.shadcn.com/docs/installation](https://ui.shadcn.com/docs/installation)

### 2. Run agentex-ui-kit locally

```bash
# in agentex/agentex-ui-kit

# serve components on port 3000 (do not change the port!)
npm run dev
```

### 3. Install components in your project

```bash
# Install root context component
npx shadcn@latest add http://localhost:3000/r/agentex-root.json

# Install task context component
npx shadcn@latest add http://localhost:3000/r/agentex-task.json

# see available components
ls $REPLACE_ME/agentex/agentex-ui-kit/public/r/
```

### Basic Usage

See [ARCHITECTURE.md](./ARCHITECTURE.md) for details.

```tsx
import { AgentexRoot } from "@/components/agentex-root";
import { useAgentexRootStore } from "@/hooks/use-agentex-root-store";
import { useAgentexRootController } from "@/hooks/use-agentex-root-controller";

import { AgentexTask } from "@/components/agentex-task";
import { useAgentexTaskStore } from "@/hooks/use-agentex-task-store";
import { useAgentexTaskController } from "@/hooks/use-agentex-task-controller";

import AgentexSDK from "agentex";
import { useState } from "react";

function TaskView() {
  const messages = useAgentexTaskStore(state => state.messages);
  const { isSendMessageEnabled, sendMessage } = useAgentexTaskController();
  return <>TODO</>;
}

function CreateTaskView() {
  const { createTask } = useAgentexRootController();
  return <>TODO</>;
}

/**
 * This example view-controller just displays the first task if it exists,
 * but in reality you might want to allow users to select a task.
 */
function ViewController() {
  const firstTask = useAgentexRootStore(state => state.tasks[0]);

  if (firstTask) {
    return (
      <AgentexTask taskID={firstTask.id}>
        <TaskView />
      </AgentexTask>
    );
  }

  return <CreateTaskView />;
}

export default function App() {
  const [agentexClient] = useState(() => new AgentexSDK(/* Your configs here */));

  return (
    <AgentexRoot agentexClient={agentexClient}>
      <ViewController />
    </AgentexRoot>
  );
}
```

## Development Commands

```bash
npm run dev        # Start development server
npm run build      # Build for production  
npm run start      # Start production server
npm run lint       # Run ESLint
npm run typecheck  # Run TypeScript checking
npm run test       # Run Jest tests
```

## Feedback

This project is being developed quickly! Please share feedback with @charlotte.
