import { TaskMessageDataContentComponent } from "@/registry/agentex/task-message-data-content/task-message-data-content";
import { TaskMessageReasoningContentComponent } from "@/registry/agentex/task-message-reasoning-content/task-message-reasoning-content";
import { TaskMessageTextContentComponent } from "@/registry/agentex/task-message-text-content/task-message-text-content";
import {
  MemoizedTaskMessageToolPairComponent,
  TaskMessageToolPairComponent,
} from "@/registry/agentex/task-message-tool-pair/task-message-tool-pair";
import type {
  TaskMessage,
  ToolRequestContent,
  ToolResponseContent,
} from "agentex/resources";
import { memo, useMemo } from "react";

type TaskMessageComponentProps = {
  message: TaskMessage;
  theme: "dark" | "light";
};

function TaskMessageComponent({ message, theme }: TaskMessageComponentProps) {
  if (message.content.type === "text") {
    return (
      <TaskMessageTextContentComponent
        content={message.content}
        theme={theme}
      />
    );
  }
  if (message.content.type === "data") {
    return (
      <TaskMessageDataContentComponent
        content={message.content}
        theme={theme}
      />
    );
  }
  if (message.content.type === "reasoning") {
    return <TaskMessageReasoningContentComponent content={message.content} />;
  }

  message.content.type satisfies "tool_request" | "tool_response" | undefined;

  return null;
}

const MemoizedTaskMessageComponent = memo(TaskMessageComponent);

type TaskMessagesComponentProps = {
  messages: TaskMessage[];
  theme: "dark" | "light";
};

function TaskMessagesComponent({
  messages,
  theme,
}: TaskMessagesComponentProps) {
  const toolCallIdToResponseMap = new Map(
    messages
      .filter(
        (m): m is TaskMessage & { content: ToolResponseContent } =>
          m.content.type === "tool_response"
      )
      .map((m) => [m.content.tool_call_id, m])
  );

  return (
    <>
      {messages.map((m, index) => {
        const { content } = m;
        switch (content.type) {
          case "text":
          case "data":
          case "reasoning":
            return (
              <TaskMessageComponent key={index} message={m} theme={theme} />
            );
          case "tool_request":
            return (
              <TaskMessageToolPairComponent
                key={index}
                theme={theme}
                toolRequestMessage={{
                  ...m,
                  content,
                }}
                toolResponseMessage={toolCallIdToResponseMap.get(
                  content.tool_call_id
                )}
              />
            );
          case "tool_response":
            return null;
          default:
            content.type satisfies undefined;
            return null;
        }
      })}
    </>
  );
}

function MemoizedTaskMessagesComponentImpl({
  messages,
  theme,
}: TaskMessagesComponentProps) {
  const toolCallIdToResponseMap = useMemo<
    Map<string, TaskMessage & { content: ToolResponseContent }>
  >(
    () =>
      new Map(
        messages
          .filter(
            (m): m is TaskMessage & { content: ToolResponseContent } =>
              m.content.type === "tool_response"
          )
          .map((m) => [m.content.tool_call_id, m])
      ),
    [messages]
  );

  return (
    <>
      {messages.map((m, index) => {
        switch (m.content.type) {
          case "text":
          case "data":
          case "reasoning":
            return (
              <MemoizedTaskMessageComponent
                key={index}
                message={m}
                theme={theme}
              />
            );
          case "tool_request":
            return (
              <MemoizedTaskMessageToolPairComponent
                key={index}
                theme={theme}
                toolRequestMessage={
                  m as TaskMessage & { content: ToolRequestContent }
                }
                toolResponseMessage={toolCallIdToResponseMap.get(
                  m.content.tool_call_id
                )}
              />
            );
          case "tool_response":
            return null;
          default:
            m.content.type satisfies undefined;
            return null;
        }
      })}
    </>
  );
}

const MemoizedTaskMessagesComponent = memo(MemoizedTaskMessagesComponentImpl);

export { MemoizedTaskMessagesComponent, TaskMessagesComponent };
