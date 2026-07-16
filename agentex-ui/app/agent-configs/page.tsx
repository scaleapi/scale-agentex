'use client';

import { useEffect, useMemo, useState } from 'react';

import { useRouter } from 'next/navigation';

import AgentexSDK from 'agentex';
import { agentRPCNonStreaming } from 'agentex/lib';

import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';

type AgentConfig = {
  id: string;
  name: string;
  description: string | null;
  system_prompt: string;
  harness: string;
  allowed_tools: string[];
  model: string;
  created_at: string;
  updated_at: string;
};

const DEFAULT_AGENT_NAME = 'golden-agent';

const AGENTEX_API_BASE_URL =
  process.env.NEXT_PUBLIC_AGENTEX_API_BASE_URL ?? 'http://localhost:5004';

export default function AgentConfigsPage() {
  const router = useRouter();

  const agentexClient = useMemo(
    () =>
      new AgentexSDK({
        baseURL: AGENTEX_API_BASE_URL,
        fetchOptions: { credentials: 'include' },
      }),
    []
  );

  const [configs, setConfigs] = useState<AgentConfig[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);

  // Per-config launcher state — keyed by config id so each card has its own
  // textarea + agent-name input + busy flag.
  const [launchState, setLaunchState] = useState<
    Record<string, { message: string; agentName: string; busy: boolean }>
  >({});

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch('/api/agent-configs');
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setConfigs(Array.isArray(data?.items) ? data.items : []);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load agent configs');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  function updateLaunch(
    id: string,
    patch: Partial<{ message: string; agentName: string; busy: boolean }>
  ) {
    setLaunchState(prev => ({
      ...prev,
      [id]: {
        message: prev[id]?.message ?? '',
        agentName: prev[id]?.agentName ?? DEFAULT_AGENT_NAME,
        busy: false,
        ...patch,
      },
    }));
  }

  async function launchWithConfig(config: AgentConfig) {
    const state = launchState[config.id];
    const message = (state?.message ?? '').trim();
    const agentName = (state?.agentName ?? DEFAULT_AGENT_NAME).trim();
    if (!message) {
      setError('Enter a message before launching.');
      return;
    }
    setError(null);
    updateLaunch(config.id, { busy: true });

    try {
      // task/create — pass the agent config as params. The golden agent reads
      // system_prompt / allowed_tools / harness / model off task params.
      const createResp = await agentRPCNonStreaming(
        agentexClient,
        { agentName },
        'task/create',
        {
          params: {
            system_prompt: config.system_prompt,
            allowed_tools: config.allowed_tools,
            harness: config.harness,
            model: config.model,
            // attach the source config id so traces can be cross-referenced.
            agent_config_id: config.id,
          },
        }
      );
      if (createResp.error) throw new Error(createResp.error.message);
      const task = createResp.result as { id: string };

      // First user message — agent's acp_type is `async`, so use event/send.
      const sendResp = await agentRPCNonStreaming(
        agentexClient,
        { agentName },
        'event/send',
        {
          task_id: task.id,
          content: {
            type: 'text',
            author: 'user',
            format: 'plain',
            attachments: [],
            content: message,
          },
        }
      );
      if (sendResp.error) throw new Error(sendResp.error.message);

      // Hand off to the main UI so the user can watch streaming output.
      // useSafeSearchParams reads agent_name + task_id from the URL.
      const params = new URLSearchParams({
        agent_name: agentName,
        task_id: task.id,
      });
      router.push(`/?${params.toString()}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Launch failed');
      updateLaunch(config.id, { busy: false });
    }
  }

  return (
    <div className="mx-auto max-w-5xl space-y-10 px-6 py-10">
      <header>
        <h1 className="text-2xl font-semibold">Agent configs</h1>
        <p className="text-muted-foreground mt-1 text-sm">
          Pick a config from pubsec-dev SGP (via the forwarded{' '}
          <code>egp-api-backend</code>), type a message, and dispatch it to a
          locally running agent through your local agentex (
          <code>{AGENTEX_API_BASE_URL}</code>). Default target is{' '}
          <code>{DEFAULT_AGENT_NAME}</code>.
        </p>
      </header>

      {error && (
        <div
          role="alert"
          className="border-destructive bg-destructive/10 text-destructive rounded-md border p-3 text-sm whitespace-pre-wrap"
        >
          {error}
        </div>
      )}

      <section>
        <h2 className="mb-3 text-lg font-medium">Launch a session</h2>
        {loading ? (
          <p className="text-muted-foreground text-sm">Loading…</p>
        ) : configs.length === 0 ? (
          <p className="text-muted-foreground text-sm">No configs yet.</p>
        ) : (
          <ul className="space-y-4">
            {configs.map(c => {
              const s = launchState[c.id] ?? {
                message: '',
                agentName: DEFAULT_AGENT_NAME,
                busy: false,
              };
              return (
                <li
                  key={c.id}
                  className="border-border space-y-3 rounded-md border p-4"
                >
                  <div className="flex items-baseline justify-between gap-3">
                    <div>
                      <div className="font-medium">{c.name}</div>
                      {c.description && (
                        <div className="text-muted-foreground mt-1 text-sm">
                          {c.description}
                        </div>
                      )}
                    </div>
                    <code className="text-muted-foreground text-xs">
                      {c.id}
                    </code>
                  </div>

                  <div className="flex flex-wrap gap-2 text-xs">
                    <span className="bg-muted rounded px-2 py-0.5">
                      harness: {c.harness}
                    </span>
                    <span className="bg-muted rounded px-2 py-0.5">
                      model: {c.model}
                    </span>
                    {c.allowed_tools.map(t => (
                      <span
                        key={t}
                        className="bg-muted text-muted-foreground rounded px-2 py-0.5"
                      >
                        {t}
                      </span>
                    ))}
                  </div>

                  <details className="text-xs">
                    <summary className="text-muted-foreground cursor-pointer">
                      System prompt
                    </summary>
                    <pre className="bg-muted mt-2 rounded p-2 text-xs whitespace-pre-wrap">
                      {c.system_prompt}
                    </pre>
                  </details>

                  <div className="grid grid-cols-[1fr_auto] items-end gap-3">
                    <div className="space-y-1">
                      <Label htmlFor={`msg-${c.id}`}>First message</Label>
                      <Textarea
                        id={`msg-${c.id}`}
                        value={s.message}
                        onChange={e =>
                          updateLaunch(c.id, { message: e.target.value })
                        }
                        rows={3}
                        placeholder="What should the agent do?"
                      />
                    </div>
                    <div className="w-56 space-y-1">
                      <Label htmlFor={`agent-${c.id}`}>Agent name</Label>
                      <input
                        id={`agent-${c.id}`}
                        value={s.agentName}
                        onChange={e =>
                          updateLaunch(c.id, { agentName: e.target.value })
                        }
                        className="border-input w-full rounded-md border px-3 py-2 text-sm"
                      />
                      <Button
                        type="button"
                        className="mt-2 w-full"
                        disabled={s.busy || !s.message.trim()}
                        onClick={() => launchWithConfig(c)}
                      >
                        {s.busy ? 'Launching…' : 'Launch'}
                      </Button>
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      <section>
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-medium">Create a config</h2>
          <Button
            type="button"
            variant="ghost"
            onClick={() => setShowCreate(s => !s)}
          >
            {showCreate ? 'Hide' : 'Show'}
          </Button>
        </div>
        {showCreate && <CreateForm onCreated={refresh} setError={setError} />}
      </section>
    </div>
  );
}

// ----- Create form (secondary; collapsed by default) -----------------------

function CreateForm({
  onCreated,
  setError,
}: {
  onCreated: () => void;
  setError: (e: string | null) => void;
}) {
  const EMPTY = {
    name: '',
    description: '',
    system_prompt: '',
    harness: 'claude-code',
    model: 'claude-opus-4-6',
    allowed_tools: 'Read,Write,Bash,WebFetch',
  };
  const [form, setForm] = useState(EMPTY);
  const [submitting, setSubmitting] = useState(false);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const allowed_tools = form.allowed_tools
        .split(',')
        .map(s => s.trim())
        .filter(Boolean);
      const res = await fetch('/api/agent-configs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: form.name,
          description: form.description || undefined,
          system_prompt: form.system_prompt,
          harness: form.harness,
          model: form.model,
          allowed_tools,
        }),
      });
      if (!res.ok) throw new Error(await res.text());
      setForm(EMPTY);
      onCreated();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Create failed');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleCreate} className="mt-3 space-y-4">
      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-1">
          <Label htmlFor="name">Name</Label>
          <input
            id="name"
            value={form.name}
            onChange={e => setForm({ ...form, name: e.target.value })}
            required
            className="border-input w-full rounded-md border px-3 py-2 text-sm"
          />
        </div>
        <div className="space-y-1">
          <Label htmlFor="model">Model</Label>
          <input
            id="model"
            value={form.model}
            onChange={e => setForm({ ...form, model: e.target.value })}
            required
            className="border-input w-full rounded-md border px-3 py-2 text-sm"
          />
        </div>
        <div className="space-y-1">
          <Label htmlFor="harness">Harness</Label>
          <input
            id="harness"
            value={form.harness}
            onChange={e => setForm({ ...form, harness: e.target.value })}
            required
            className="border-input w-full rounded-md border px-3 py-2 text-sm"
            placeholder="claude-code | codex | litellm"
          />
        </div>
        <div className="space-y-1">
          <Label htmlFor="tools">Allowed tools (comma-separated)</Label>
          <input
            id="tools"
            value={form.allowed_tools}
            onChange={e => setForm({ ...form, allowed_tools: e.target.value })}
            className="border-input w-full rounded-md border px-3 py-2 text-sm"
          />
        </div>
      </div>

      <div className="space-y-1">
        <Label htmlFor="description">Description</Label>
        <input
          id="description"
          value={form.description}
          onChange={e => setForm({ ...form, description: e.target.value })}
          className="border-input w-full rounded-md border px-3 py-2 text-sm"
        />
      </div>

      <div className="space-y-1">
        <Label htmlFor="system_prompt">System prompt</Label>
        <Textarea
          id="system_prompt"
          value={form.system_prompt}
          onChange={e => setForm({ ...form, system_prompt: e.target.value })}
          required
          rows={6}
        />
      </div>

      <div className="flex justify-end">
        <Button type="submit" disabled={submitting}>
          {submitting ? 'Creating…' : 'Create'}
        </Button>
      </div>
    </form>
  );
}
