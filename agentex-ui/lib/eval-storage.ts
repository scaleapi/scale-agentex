export type ConversationMessage = {
  role: 'user' | 'assistant' | 'tool';
  content: string;
  tool_calls?: { name: string; arguments: Record<string, unknown> }[];
  name?: string;
};

export type EvalCase = {
  id: string;
  input: string;
  expected_output: string;
  actual_output: string;
  conversation: ConversationMessage[];
  tags: string[];
  source: 'ui_capture';
  captured_at: string;
  notes: string;
};

export type EvalSet = {
  name: string;
  agent_name: string;
  agent_id: string;
  items: EvalCase[];
};

const STORAGE_KEY = 'agentex-eval-sets';

export function getEvalSets(): Record<string, EvalSet> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
}

export function getEvalSet(agentName: string): EvalSet | null {
  const sets = getEvalSets();
  return sets[agentName] ?? null;
}

export function saveEvalCase(
  agentName: string,
  agentId: string,
  evalCase: EvalCase
): EvalSet {
  const sets = getEvalSets();

  if (!sets[agentName]) {
    sets[agentName] = {
      name: `${agentName}_evals`,
      agent_name: agentName,
      agent_id: agentId,
      items: [],
    };
  }

  sets[agentName].items.push(evalCase);
  localStorage.setItem(STORAGE_KEY, JSON.stringify(sets));

  return sets[agentName];
}

export function deleteEvalCase(agentName: string, evalId: string): void {
  const sets = getEvalSets();
  if (!sets[agentName]) return;

  sets[agentName].items = sets[agentName].items.filter(
    item => item.id !== evalId
  );
  localStorage.setItem(STORAGE_KEY, JSON.stringify(sets));
}

export function exportEvalSet(agentName: string): string | null {
  const set = getEvalSet(agentName);
  if (!set) return null;
  return JSON.stringify(set, null, 2);
}
