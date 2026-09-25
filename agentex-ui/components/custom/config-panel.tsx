'use client';

import { useCallback, useEffect } from 'react';

import { RotateCcw } from 'lucide-react';
import { useForm } from 'react-hook-form';

import { TagInput } from '@/components/custom/tag-input';
import { Button } from '@/components/ui/button';
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
} from '@/components/ui/form';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';

export type GoldenAgentConfig = {
  harness: string;
  model: string;
  system_prompt: string;
  allowed_tools: string[];
};

const SUPPORTED_HARNESSES = [
  'sandbox-claude',
  'claude-code',
  'codex',
  'agentex',
] as const;

const DEFAULT_MODEL_BY_HARNESS: Record<string, string> = {
  'sandbox-claude': 'claude-opus-4-6',
  'claude-code': 'claude-opus-4-6',
  codex: 'gpt-5.4',
  agentex: 'gpt-5.4',
};

export const DEFAULT_CONFIG: GoldenAgentConfig = {
  harness: 'sandbox-claude',
  model: 'claude-opus-4-6',
  system_prompt:
    "You are a developer for Scale AI's SGP team. Your primary sources of truth are scaleapi/packages/egp-api-backend and scaleapi/packages/egp-annotation. Use these packages to do the development you need to do. Make sure to read the READMEs and CLAUDE.mds in those directories to get the context you need to address any issues. Your main goal is to take in the information from the prompt, use your sources of truth to come up with a course of action to address it, and then make a PR with the solution.",
  allowed_tools: [
    'Read',
    'Write',
    'Edit',
    'Glob',
    'Grep',
    'Bash',
    'WebSearch',
    'WebFetch',
    'List',
  ],
};

type ConfigPanelProps = {
  disabled: boolean;
  onConfigChange: (config: GoldenAgentConfig) => void;
  onReset: () => void;
};

export function ConfigPanel({
  disabled,
  onConfigChange,
  onReset,
}: ConfigPanelProps) {
  const form = useForm<GoldenAgentConfig>({
    defaultValues: DEFAULT_CONFIG,
  });

  const harness = form.watch('harness');

  useEffect(() => {
    const subscription = form.watch(values => {
      onConfigChange(values as GoldenAgentConfig);
    });
    return () => subscription.unsubscribe();
  }, [form, onConfigChange]);

  const handleHarnessChange = useCallback(
    (value: string) => {
      form.setValue('harness', value);
      form.setValue('model', DEFAULT_MODEL_BY_HARNESS[value] ?? '');
    },
    [form]
  );

  const handleReset = useCallback(() => {
    form.reset(DEFAULT_CONFIG);
    onReset();
  }, [form, onReset]);

  return (
    <div className="flex h-full flex-col">
      <div className="border-b px-4 py-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold">Configuration</h2>
          {disabled && (
            <Button
              variant="ghost"
              size="sm"
              onClick={handleReset}
              className="gap-1.5 text-xs"
            >
              <RotateCcw className="size-3" />
              New Chat
            </Button>
          )}
        </div>
        <p className="text-muted-foreground mt-0.5 text-xs">golden-agent</p>
      </div>

      <Form {...form}>
        <form className="flex-1 space-y-4 overflow-y-auto p-4">
          <FormField
            control={form.control}
            name="harness"
            render={({ field }) => (
              <FormItem>
                <FormLabel className="text-xs">Harness</FormLabel>
                <Select
                  value={field.value}
                  onValueChange={handleHarnessChange}
                  disabled={disabled}
                >
                  <FormControl>
                    <SelectTrigger className="w-full">
                      <SelectValue />
                    </SelectTrigger>
                  </FormControl>
                  <SelectContent>
                    {SUPPORTED_HARNESSES.map(h => (
                      <SelectItem key={h} value={h}>
                        {h}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="model"
            render={({ field }) => (
              <FormItem>
                <FormLabel className="text-xs">Model</FormLabel>
                <FormControl>
                  <input
                    type="text"
                    value={field.value}
                    onChange={field.onChange}
                    disabled={disabled}
                    placeholder={
                      DEFAULT_MODEL_BY_HARNESS[harness] ?? 'Enter model name'
                    }
                    className="border-input placeholder:text-muted-foreground flex h-9 w-full rounded-md border bg-transparent px-3 py-1 text-sm shadow-xs outline-none focus-visible:ring-[1px] focus-visible:ring-[#756BA2] disabled:cursor-not-allowed disabled:opacity-50"
                  />
                </FormControl>
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="system_prompt"
            render={({ field }) => (
              <FormItem>
                <FormLabel className="text-xs">System Prompt</FormLabel>
                <FormControl>
                  <Textarea
                    value={field.value}
                    onChange={field.onChange}
                    disabled={disabled}
                    placeholder="Enter system instructions..."
                    className="min-h-32 resize-y"
                  />
                </FormControl>
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="allowed_tools"
            render={({ field }) => (
              <FormItem>
                <FormLabel className="text-xs">Allowed Tools</FormLabel>
                <FormControl>
                  <TagInput
                    value={field.value}
                    onChange={field.onChange}
                    disabled={disabled}
                    placeholder="Add tool name and press Enter"
                  />
                </FormControl>
              </FormItem>
            )}
          />
        </form>
      </Form>
    </div>
  );
}
