'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import type {
  MemoryPreview,
  MemoryState,
  StrategyItem,
} from '@/lib/memory-types';

// Memory server URL - defaults to local development server
const MEMORY_SERVER_URL =
  process.env.NEXT_PUBLIC_MEMORY_SERVER_URL || 'http://localhost:8765';

export const memoryKeys = {
  all: ['memory'] as const,
  byAgent: (agentId: string | null) =>
    agentId ? ([...memoryKeys.all, agentId] as const) : memoryKeys.all,
  preview: (agentId: string | null, userId: string | null) =>
    agentId
      ? ([...memoryKeys.all, agentId, userId, 'preview'] as const)
      : memoryKeys.all,
};

/**
 * Fetches agent memory strategies from the standalone memory server.
 */
export function useMemory(
  agentId: string | null,
  userId: string | null = 'default'
): MemoryState {
  const { data, isLoading, error } = useQuery<
    { agentStrategies: StrategyItem[]; userStrategies: StrategyItem[] },
    Error
  >({
    queryKey: memoryKeys.byAgent(agentId),
    queryFn: async () => {
      if (!agentId) {
        return { agentStrategies: [], userStrategies: [] };
      }

      const response = await fetch(
        `${MEMORY_SERVER_URL}/api/memory/${encodeURIComponent(agentId)}?user_id=${encodeURIComponent(userId || 'default')}`
      );

      if (!response.ok) {
        throw new Error(`Failed to fetch memory: ${response.statusText}`);
      }

      const data = await response.json();
      return {
        agentStrategies: data.agent_strategies || [],
        userStrategies: data.user_strategies || [],
      };
    },
    enabled: agentId !== null,
    retry: 1,
    staleTime: 30000, // Cache for 30 seconds
  });

  return {
    agentStrategies: data?.agentStrategies ?? [],
    userStrategies: data?.userStrategies ?? [],
    isLoading,
    error: error?.message ?? null,
  };
}

/**
 * Fetches preview of what gets injected into the prompt.
 */
export function useMemoryPreview(
  agentId: string | null,
  userId: string | null = 'default'
): { preview: MemoryPreview | null; isLoading: boolean; error: string | null } {
  const { data, isLoading, error } = useQuery<MemoryPreview, Error>({
    queryKey: memoryKeys.preview(agentId, userId),
    queryFn: async () => {
      if (!agentId) {
        return { content: '', strategyCount: 0 };
      }

      const response = await fetch(
        `${MEMORY_SERVER_URL}/api/memory/${encodeURIComponent(agentId)}/preview?user_id=${encodeURIComponent(userId || 'default')}`
      );

      if (!response.ok) {
        throw new Error(`Failed to fetch preview: ${response.statusText}`);
      }

      const data = await response.json();
      return {
        content: data.content,
        strategyCount: data.strategy_count,
      };
    },
    enabled: agentId !== null,
    retry: 1,
    staleTime: 30000,
  });

  return {
    preview: data ?? null,
    isLoading,
    error: error?.message ?? null,
  };
}

/**
 * Hook to delete a strategy.
 */
export function useDeleteStrategy() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      strategyId,
      agentId,
    }: {
      strategyId: string;
      agentId: string;
    }) => {
      const response = await fetch(
        `${MEMORY_SERVER_URL}/api/memory/strategy/${encodeURIComponent(strategyId)}?agent_id=${encodeURIComponent(agentId)}`,
        { method: 'DELETE' }
      );

      if (!response.ok) {
        throw new Error(`Failed to delete strategy: ${response.statusText}`);
      }

      return response.json();
    },
    onSuccess: (_, { agentId }) => {
      queryClient.invalidateQueries({ queryKey: memoryKeys.byAgent(agentId) });
      queryClient.invalidateQueries({
        queryKey: memoryKeys.preview(agentId, null),
      });
    },
  });
}

/**
 * Hook to trigger strategy extraction.
 */
export function useExtractStrategies() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      agentId,
      hours = 24,
      userId = 'default',
    }: {
      agentId: string;
      hours?: number;
      userId?: string;
    }) => {
      const response = await fetch(
        `${MEMORY_SERVER_URL}/api/memory/${encodeURIComponent(agentId)}/extract`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ hours, user_id: userId }),
        }
      );

      if (!response.ok) {
        throw new Error(`Failed to extract strategies: ${response.statusText}`);
      }

      return response.json();
    },
    onSuccess: (_, { agentId }) => {
      queryClient.invalidateQueries({ queryKey: memoryKeys.byAgent(agentId) });
      queryClient.invalidateQueries({
        queryKey: memoryKeys.preview(agentId, null),
      });
    },
  });
}

/**
 * Hook to manually add a strategy.
 */
export function useAddStrategy() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      agentId,
      title,
      description,
      principles,
      outcome = 'success',
      domain,
      level = 'agent',
      userId = 'default',
    }: {
      agentId: string;
      title: string;
      description: string;
      principles: string[];
      outcome?: string;
      domain?: string;
      level?: string;
      userId?: string;
    }) => {
      const response = await fetch(
        `${MEMORY_SERVER_URL}/api/memory/${encodeURIComponent(agentId)}/add?user_id=${encodeURIComponent(userId)}`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            title,
            description,
            principles,
            outcome,
            domain,
            level,
          }),
        }
      );

      if (!response.ok) {
        throw new Error(`Failed to add strategy: ${response.statusText}`);
      }

      return response.json();
    },
    onSuccess: (_, { agentId }) => {
      queryClient.invalidateQueries({ queryKey: memoryKeys.byAgent(agentId) });
      queryClient.invalidateQueries({
        queryKey: memoryKeys.preview(agentId, null),
      });
    },
  });
}
