"use client";

import { Button } from "@/components/ui/button";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { zodResolver } from "@hookform/resolvers/zod";
import type { Agent, DataContent, TextContent } from "agentex/resources";
import {
  createContext,
  ReactElement,
  ReactNode,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";
import {
  Control,
  useForm,
  UseFormHandleSubmit,
  UseFormReset,
  UseFormSetValue,
  UseFormWatch,
} from "react-hook-form";
import { z } from "zod";
import { createStore, useStore } from "zustand";

type FormStoreProps = {
  theme: "light" | "dark";
  agentOptions: Agent[];
  onSubmit: (data: FormData, resetForm: (formData?: FormData) => void) => void;
  defaultValuesFromParent: CustomPartial<FormData> | undefined;
  control: Control<FormData>;
  setValue: UseFormSetValue<FormData>;
  watch: UseFormWatch<FormData>;
  handleSubmit: UseFormHandleSubmit<FormData>;
  reset: UseFormReset<FormData>;
};

type FormStoreState = FormStoreProps;

function createFormStore(initialState: FormStoreProps) {
  return createStore<FormStoreState>()(() => ({
    ...initialState,
  }));
}

type FormStore = ReturnType<typeof createFormStore>;

const FormContext = createContext<FormStore | null>(null);

const formDataSchema = z.object({
  kind: z.enum(["text", "data"]),
  textContent: z.string().max(100_000),
  dataContent: z
    .string()
    .max(100_000)
    .superRefine((arg, ctx) => {
      if (!arg) {
        return;
      }
      try {
        const jsonValue = JSON.parse(arg);
        const recordParseResult = z
          .record(z.string(), z.any())
          .safeParse(jsonValue);
        if (!recordParseResult.success) {
          for (const issue of recordParseResult.error.issues) {
            ctx.addIssue(issue);
          }
        }
      } catch {
        ctx.addIssue({
          code: "custom",
          message: "Data must be a valid JSON object",
        });
      }
    }),
  agentID: z.string().min(1, "Agent is required"),
});

type FormData = z.infer<typeof formDataSchema>;

type CustomPartial<T> = { [P in keyof T]?: T[P] | null | undefined };

function createDefaultValues(
  agentOptions: Agent[],
  defaultValues?: CustomPartial<FormData>
): FormData {
  const defaultAgentIDFromDefaultValues = agentOptions.some(
    (agent) => agent.id === defaultValues?.agentID
  )
    ? defaultValues?.agentID
    : undefined;

  const defaultAgentIDFromAgentOptions =
    agentOptions.length === 1 ? agentOptions[0]?.id : undefined;

  return {
    kind: defaultValues?.kind ?? "text",
    textContent: defaultValues?.textContent ?? "",
    dataContent: defaultValues?.dataContent ?? "",
    agentID:
      defaultAgentIDFromDefaultValues ?? defaultAgentIDFromAgentOptions ?? "",
  };
}

function CreateUserMessageFormContent() {
  const store = useContext(FormContext);
  if (store === null) {
    throw new Error(
      "CreateUserMessageFormContent must be used within a CreateUserMessageForm"
    );
  }

  const control = useStore(store, (s) => s.control);
  const agentOptions = useStore(store, (s) => s.agentOptions);
  const onSubmit = useStore(store, (s) => s.onSubmit);
  const formHandleSubmit = useStore(store, (s) => s.handleSubmit);
  const setValue = useStore(store, (s) => s.setValue);

  const handleSubmit = formHandleSubmit((data) => {
    onSubmit(data, (resetFormData) => {
      const currentStoreState = store.getState();
      currentStoreState.reset(
        resetFormData ??
          createDefaultValues(
            currentStoreState.agentOptions,
            currentStoreState.defaultValuesFromParent
          )
      );
    });
  });

  return (
    <form onSubmit={handleSubmit} className="space-y-8">
      <FormField
        control={control}
        name="kind"
        render={({ field: kindField }) => (
          <Tabs
            value={kindField.value}
            onValueChange={(value) => {
              switch (value) {
                case "text":
                  setValue("kind", "text");
                  break;
                case "data":
                  setValue("kind", "data");
                  break;
              }
            }}
          >
            <div className="flex items-baseline-last gap-2">
              <span className="text-sidebar-foreground">Message type: </span>
              <TabsList>
                <TabsTrigger value="text">Text</TabsTrigger>
                <TabsTrigger value="data">Data</TabsTrigger>
              </TabsList>
            </div>

            <TabsContent value="text">
              <FormField
                control={control}
                name="textContent"
                render={({ field }) => (
                  <FormItem
                    onKeyDown={(e) => {
                      if (
                        e.key === "Enter" &&
                        !e.shiftKey &&
                        !e.ctrlKey &&
                        !e.metaKey &&
                        !e.altKey
                      ) {
                        e.preventDefault();
                        handleSubmit(e);
                      }
                    }}
                  >
                    <FormLabel hidden>Message Text Content</FormLabel>
                    <FormControl>
                      <Textarea
                        placeholder="Type your message here..."
                        {...field}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </TabsContent>

            <TabsContent value="data">
              <FormField
                control={control}
                name="dataContent"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel hidden>Message Data Content</FormLabel>
                    <FormControl>
                      <Textarea
                        placeholder="Enter JSON here..."
                        className="text-mono"
                        {...field}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </TabsContent>
          </Tabs>
        )}
      />

      <div className="flex justify-between gap-2 items-baseline-last">
        <FormField
          control={control}
          name="agentID"
          render={({ field }) => (
            <FormItem className="flex gap-2 items-baseline-last">
              <FormLabel>Agent</FormLabel>
              <FormControl>
                <Select
                  onValueChange={field.onChange}
                  defaultValue={field.value}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Select an agent" />
                  </SelectTrigger>
                  <SelectContent>
                    {agentOptions.map((agent) => (
                      <SelectItem key={agent.id} value={agent.id}>
                        {agent.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        <Button type="submit">Send Message</Button>
      </div>
    </form>
  );
}

function CreateUserMessageFormSelectedAgent({
  render,
}: {
  render: ({ agent }: { agent: Agent | null }) => ReactElement;
}) {
  const store = useContext(FormContext);
  if (store === null) {
    throw new Error(
      "CreateUserMessageFormSelectedAgent must be used within a CreateUserMessageForm"
    );
  }

  const selectedAgentID = useStore(store, (s) => s.watch("agentID"));
  const agentOptions = useStore(store, (s) => s.agentOptions);

  const selectedAgent = agentOptions.find(
    (agent) => agent.id === selectedAgentID
  );

  return render({ agent: selectedAgent ?? null });
}

function CreateUserMessageForm({
  children,
  defaultValues,
  agentOptions,
  disabled,
  theme,
  onSubmit,
}: {
  children?: ReactNode;
  defaultValues?: CustomPartial<FormData>;
  agentOptions: Agent[];
  disabled?: boolean;
  theme: "light" | "dark";
  onSubmit: (
    data:
      | { kind: "text"; content: TextContent["content"]; agentID: Agent["id"] }
      | { kind: "data"; content: DataContent["data"]; agentID: Agent["id"] },
    resetForm: (formData?: FormData) => void
  ) => void;
}) {
  const form = useForm<FormData>({
    resolver: zodResolver(formDataSchema),
    defaultValues: createDefaultValues(agentOptions, defaultValues),
    disabled: !!disabled,
  });
  // form doesn't change value when these ones do
  // so we can't just pass the entire form into zustand
  // or state won't update
  const { control, handleSubmit, setValue, watch, reset } = form;

  const onSubmitRef = useRef(onSubmit);
  useEffect(() => {
    onSubmitRef.current = onSubmit;
  }, [onSubmit]);

  const [store] = useState(() =>
    createFormStore({
      theme,
      agentOptions,
      control,
      setValue,
      watch,
      handleSubmit,
      reset,
      defaultValuesFromParent: defaultValues,
      onSubmit: (data, ...args) =>
        onSubmitRef.current(
          {
            ...data,
            content:
              data.kind === "data"
                ? JSON.parse(data.dataContent)
                : data.textContent,
          },
          ...args
        ),
    })
  );

  // keep store state in sync
  useEffect(() => {
    store.setState({ theme });
  }, [store, theme]);

  useEffect(() => {
    store.setState({ agentOptions });
  }, [store, agentOptions]);

  useEffect(() => {
    store.setState({ control });
  }, [store, control]);

  useEffect(() => {
    store.setState({ setValue });
  }, [store, setValue]);

  useEffect(() => {
    store.setState({ watch });
  }, [store, watch]);

  useEffect(() => {
    store.setState({ handleSubmit });
  }, [store, handleSubmit]);

  useEffect(() => {
    store.setState({ reset });
  }, [store, reset]);

  useEffect(() => {
    store.setState({ defaultValuesFromParent: defaultValues });
  }, [store, defaultValues]);

  return (
    <Form {...form}>
      <FormContext.Provider value={store}>{children}</FormContext.Provider>
    </Form>
  );
}

type CreateUserMessageDefaultValues = CustomPartial<FormData>;

export {
  CreateUserMessageForm,
  CreateUserMessageFormContent,
  CreateUserMessageFormSelectedAgent
};
export type {
  CreateUserMessageDefaultValues,
  FormData as CreateUserMessageFormData
};

