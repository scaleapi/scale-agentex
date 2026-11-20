## `agentex-ui/` (Agentex UI)

The UI is a Next.js application (App Router) that provides a developer interface for:

- browsing and selecting agents
- creating tasks and monitoring task state
- chatting with agents (including streaming responses)
- inspecting execution traces/spans

### Tech stack

- **Next.js** 15 (App Router) + **React** 19
- **TypeScript**
- **Tailwind CSS** + Radix UI primitives / shadcn-style components
- **React Query** for server state and caching

### Entry points

- **App shell**: `app/layout.tsx`
- **Main page**: `app/page.tsx`
- **Primary UI composition**: `components/agentex-ui-root.tsx` and `components/primary-content/*`

### Data access

The UI treats the backend as the source of truth and uses:

- REST/HTTP calls to fetch lists and details (agents, tasks, messages, spans).
- WebSocket subscriptions for realtime task updates (especially for async agents).

Most data access is wrapped behind hooks in `hooks/` (React Query + subscription helpers).

### Running locally

From `agentex-ui/`:

```bash
npm install
cp example.env.development .env.development
npm run dev
```

The backend should be running separately (see `agentex/` docs).

