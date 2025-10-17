"use client";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { cn } from "@/lib/utils";
import {
  useAgentexDevRootSetupStore,
} from "@/registry/agentex/agentex-dev-root/hooks/use-agentex-dev-root-setup";
import { SetupFormData, SetupFormDataSchema } from "@/registry/agentex/agentex-dev-root/lib/agentex-dev-root-setup-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { ChevronsUpDown } from "lucide-react";
import { useFieldArray, useForm, UseFormReturn } from "react-hook-form";

type AgentexDevRootSetupFormDefaultHeaderFieldProps = {
  form: UseFormReturn<SetupFormData>;
  index: number;
  onDelete: (index: number) => void;
  className?: string;
};

type AgentexDevRootSetupFormCookieFieldProps = {
  form: UseFormReturn<SetupFormData>;
  index: number;
  onDelete: (index: number) => void;
  className?: string;
};

function AgentexDevRootSetupFormDefaultHeaderField({
  form,
  index,
  onDelete,
  className,
}: AgentexDevRootSetupFormDefaultHeaderFieldProps) {
  return (
    <div
      className={cn("grid grid-cols-[1fr_auto] items-center gap-2", className)}
    >
      <FormField
        control={form.control}
        name={`defaultHeaders.${index}.key`}
        render={({ field }) => (
          <FormItem>
            <FormLabel hidden>Header {index + 1}</FormLabel>
            <FormControl>
              <Input placeholder="Header: e.g. x-api-key" {...field} />
            </FormControl>
            <FormDescription hidden>The name of the header</FormDescription>
            <FormMessage />
          </FormItem>
        )}
      />
      <Button
        variant="destructive"
        type="button"
        onClick={() => onDelete(index)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            onDelete(index);
          }
        }}
      >
        Delete
      </Button>
      <FormField
        control={form.control}
        name={`defaultHeaders.${index}.value`}
        render={({ field }) => (
          <FormItem className="flex-1">
            <FormLabel hidden>Header {index + 1} Value</FormLabel>
            <FormControl>
              <Input placeholder="SOME_ENV_VAR or raw-value" {...field} />
            </FormControl>
            <FormMessage />
          </FormItem>
        )}
      />
      <FormField
        control={form.control}
        name={`defaultHeaders.${index}.fromEnv`}
        render={({ field }) => (
          <FormItem className="flex items-center gap-2">
            <FormControl>
              <Input
                type="checkbox"
                {...field}
                value={field.value ? "true" : "false"}
                checked={field.value}
              />
            </FormControl>
            <FormLabel className="text-sm">From Env</FormLabel>
          </FormItem>
        )}
      />
    </div>
  );
}

function AgentexDevRootSetupFormCookieField({
  form,
  index,
  onDelete,
  className,
}: AgentexDevRootSetupFormCookieFieldProps) {
  return (
    <div
      className={cn("grid grid-cols-[1fr_1fr_auto] items-center gap-2", className)}
    >
      <FormField
        control={form.control}
        name={`cookies.${index}.name`}
        render={({ field }) => (
          <FormItem>
            <FormLabel hidden>Cookie {index + 1} Name</FormLabel>
            <FormControl>
              <Input placeholder="Cookie name: e.g. _jwt" {...field} />
            </FormControl>
            <FormDescription hidden>The name of the cookie</FormDescription>
            <FormMessage />
          </FormItem>
        )}
      />
      <FormField
        control={form.control}
        name={`cookies.${index}.value`}
        render={({ field }) => (
          <FormItem>
            <FormLabel hidden>Cookie {index + 1} Value</FormLabel>
            <FormControl>
              <Input placeholder="Cookie value" {...field} />
            </FormControl>
            <FormMessage />
          </FormItem>
        )}
      />
      <Button
        variant="destructive"
        type="button"
        onClick={() => onDelete(index)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            onDelete(index);
          }
        }}
      >
        Delete
      </Button>
    </div>
  );
}

function AgentexDevClientSetupFormTrigger({
  ...props
}: React.ComponentProps<typeof SheetTrigger>) {
  return <SheetTrigger {...props} />;
}

function AgentexDevClientSetupFormContent({
  ...props
}: React.ComponentProps<typeof SheetContent>) {
  const onSubmit = useAgentexDevRootSetupStore((s) => s.setupFormOnSubmit);
  const defaultValues = useAgentexDevRootSetupStore(
    (s) => s.setupFormDefaultValues
  );

  const form = useForm<SetupFormData>({
    resolver: zodResolver(SetupFormDataSchema),
    defaultValues,
  });

  const defaultHeadersFieldArray = useFieldArray({
    control: form.control,
    name: "defaultHeaders",
  });

  const cookiesFieldArray = useFieldArray({
    control: form.control,
    name: "cookies",
  });

  // this component is not the view
  if (props.children !== undefined) {
    return <SheetContent {...props} />;
  }

  // this component is the view
  return (
    <SheetContent {...props}>
      <Form {...form}>
        <form
          onSubmit={form.handleSubmit((data) => {
            onSubmit(data);
            form.reset(data);
          })}
          className="space-y-8"
        >
          <SheetHeader>
            <div className="flex items-baseline-last justify-between gap-2">
              <SheetTitle>Client Setup</SheetTitle>
              <div>
                {form.formState.isDirty && (
                  <Button type="submit">
                    Save Changes
                  </Button>
                )}
              </div>
            </div>
            <SheetDescription>
              Configure the Agentex client for development purposes.
            </SheetDescription>
          </SheetHeader>

          <FormField
            control={form.control}
            name="baseURL"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Base URL</FormLabel>
                <FormControl>
                  <Input
                    placeholder="http://localhost:5003"
                    type="url"
                    {...field}
                  />
                </FormControl>
                <FormDescription>
                  Agentex URL. Defaults to your local Agentex server.
                </FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="apiKeyEnvVar"
            render={({ field }) => (
              <FormItem>
                <FormLabel>API Key Environment Variable</FormLabel>
                <FormControl>
                  <Input placeholder="SOME_ENV_VAR" {...field} />
                </FormControl>
                <FormDescription>
                  If you want to use an API key, set it as an environment
                  variable in your .env file and specify the variable name here.
                </FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />

          <p>
            Note that web clients should not be given API keys in production.
            This is for local development only. Consider cookie or token based
            authentication in production.
          </p>

          <Card>
            <Collapsible>
              <CardHeader className="flex items-center gap-4">
                <CardTitle className="w-fit">Default Headers</CardTitle>
                <CollapsibleTrigger asChild>
                  <Button variant="outline" size="icon">
                    <ChevronsUpDown />
                  </Button>
                </CollapsibleTrigger>
              </CardHeader>
              <CollapsibleContent>
                <CardContent className="flex flex-col px-8 divide-y">
                  <div className="flex gap-2 items-baseline-last py-4 justify-between">
                    <p>
                      `From Env` indicates whether the header value is the name
                      of an environment variable or the raw value itself. Use
                      environment variables for secrets. You can set environment
                      variables by creating a .env file at the root of
                      agentex-ui and restarting the app.
                    </p>
                    <Button
                      className="w-fit"
                      variant="secondary"
                      type="button"
                      onClick={() => {
                        defaultHeadersFieldArray.append({
                          key: "",
                          value: "",
                          fromEnv: true,
                        });
                      }}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          defaultHeadersFieldArray.append({
                            key: "",
                            value: "",
                            fromEnv: true,
                          });
                        }
                      }}
                    >
                      Add a default header
                    </Button>
                  </div>
                  {defaultHeadersFieldArray.fields.map((field, index) => (
                    <AgentexDevRootSetupFormDefaultHeaderField
                      key={field.id}
                      index={index}
                      form={form}
                      onDelete={defaultHeadersFieldArray.remove}
                      className="py-4"
                    />
                  ))}
                  {defaultHeadersFieldArray.fields.length === 0 && (
                    <div className="text-muted-foreground py-4">
                      (no default headers)
                    </div>
                  )}
                </CardContent>
              </CollapsibleContent>
            </Collapsible>
          </Card>

          <Card>
            <Collapsible>
              <CardHeader className="flex items-center gap-4">
                <CardTitle className="w-fit">Cookies</CardTitle>
                <CollapsibleTrigger asChild>
                  <Button variant="outline" size="icon">
                    <ChevronsUpDown />
                  </Button>
                </CollapsibleTrigger>
              </CardHeader>
              <CollapsibleContent>
                <CardContent className="flex flex-col px-8 divide-y">
                  <div className="flex gap-2 items-baseline-last py-4 justify-between">
                    <p>
                      Add cookies that will be sent with every request to the Agentex server.
                    </p>
                    <Button
                      className="w-fit"
                      variant="secondary"
                      type="button"
                      onClick={() => {
                        cookiesFieldArray.append({
                          name: "",
                          value: "",
                        });
                      }}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          cookiesFieldArray.append({
                            name: "",
                            value: "",
                          });
                        }
                      }}
                    >
                      Add a cookie
                    </Button>
                  </div>
                  {cookiesFieldArray.fields.map((field, index) => (
                    <AgentexDevRootSetupFormCookieField
                      key={field.id}
                      index={index}
                      form={form}
                      onDelete={cookiesFieldArray.remove}
                      className="py-4"
                    />
                  ))}
                  {cookiesFieldArray.fields.length === 0 && (
                    <div className="text-muted-foreground py-4">
                      (no cookies)
                    </div>
                  )}
                </CardContent>
              </CollapsibleContent>
            </Collapsible>
          </Card>

          <FormField
            control={form.control}
            name="maxRetries"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Max Retries</FormLabel>
                <FormControl>
                  <Input placeholder="3" type="number" {...field} />
                </FormControl>
                <FormDescription>
                  How many times to retry failed API calls.
                </FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="timeout"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Timeout</FormLabel>
                <FormControl>
                  <Input placeholder="300000" type="number" {...field} />
                </FormControl>
                <FormDescription>
                  Timeout for API calls in milliseconds.
                </FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />
        </form>
      </Form>
    </SheetContent>
  );
}

type AgentexDevClientSetupFormProps = {
  children?: React.ReactNode;
};

function AgentexDevClientSetupForm({
  children,
}: AgentexDevClientSetupFormProps) {
  const isSetupFormOpen = useAgentexDevRootSetupStore((s) => s.isSetupFormOpen);
  const setIsSetupFormOpen = useAgentexDevRootSetupStore(
    (s) => s.setIsSetupFormOpen
  );

  return (
    <Sheet open={isSetupFormOpen} onOpenChange={setIsSetupFormOpen}>
      {children}
    </Sheet>
  );
}

export {
  AgentexDevClientSetupForm,
  AgentexDevClientSetupFormContent,
  AgentexDevClientSetupFormTrigger
};

