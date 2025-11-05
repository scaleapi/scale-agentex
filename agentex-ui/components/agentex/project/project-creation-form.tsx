'use client';

import { motion } from 'framer-motion';
import { useForm } from 'react-hook-form';

import { useAgentexClient } from '@/components/providers/agentex-provider';
import { Button } from '@/components/ui/button';
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { toast } from '@/components/ui/toast';
import { useCreateTask } from '@/hooks/use-create-task';
import {
  SearchParamKey,
  useSafeSearchParams,
} from '@/hooks/use-safe-search-params';

type ProjectFormValues = {
  projectName: string;
  description: string;
};

export function ProjectCreationForm() {
  const { agentName, updateParams } = useSafeSearchParams();
  const { agentexClient } = useAgentexClient();
  const createTask = useCreateTask({ agentexClient });

  const form = useForm<ProjectFormValues>({
    defaultValues: {
      projectName: '',
      description: '',
    },
  });

  const handleSubmit = async (values: ProjectFormValues) => {
    if (!agentName) {
      toast.error({
        title: 'No agent selected',
        message: 'Please select an agent first.',
      });
      return;
    }

    try {
      const task = await createTask.mutateAsync({
        agentName,
        params: {
          project_name: values.projectName,
          description: values.projectName,
          content: values.projectName,
          ...(values.description.trim() && {
            project_description: values.description.trim(),
          }),
        },
      });

      updateParams({ [SearchParamKey.TASK_ID]: task.id });

      form.reset();
    } catch (error) {
      // Error handling is done in the useCreateTask hook
      console.error('Failed to create project:', error);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      className="w-full"
    >
      <Form {...form}>
        <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-6">
          <FormField
            control={form.control}
            name="projectName"
            rules={{ required: 'Project name is required' }}
            render={({ field }) => (
              <FormItem>
                <FormLabel>
                  Project Name
                  <span className="text-destructive">*</span>
                </FormLabel>
                <FormControl>
                  <Input
                    {...field}
                    type="text"
                    placeholder="Enter project name"
                    disabled={createTask.isPending}
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="description"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Description</FormLabel>
                <FormDescription>
                  Optional description for your project
                </FormDescription>
                <FormControl>
                  <Textarea
                    {...field}
                    placeholder="Enter project description"
                    rows={4}
                    className="resize-none"
                    disabled={createTask.isPending}
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          <Button
            type="submit"
            size="lg"
            disabled={createTask.isPending}
            className="w-full"
          >
            {createTask.isPending ? 'Creating Project...' : 'Create Project'}
          </Button>
        </form>
      </Form>
    </motion.div>
  );
}
