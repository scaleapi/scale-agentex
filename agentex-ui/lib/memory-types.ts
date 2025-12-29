/**
 * Types for agent memory system.
 * These mirror the types in agent_memory package.
 */

export type MemoryLevel = 'user' | 'agent';

export type SessionOutcome = 'success' | 'failure' | 'partial';

export interface StrategyItem {
  id: string;
  title: string;
  description: string;
  principles: string[];
  source_outcome: SessionOutcome;
  domain: string | null;
  confidence: number;
  created_at: string;
  usage_count: number;
}

export interface MemoryState {
  agentStrategies: StrategyItem[];
  userStrategies: StrategyItem[];
  isLoading: boolean;
  error: string | null;
}

export interface MemoryPreview {
  content: string;
  strategyCount: number;
}
