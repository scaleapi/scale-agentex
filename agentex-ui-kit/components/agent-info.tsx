import { Button } from "@/components/ui/button";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import type { Agent } from "agentex/resources";
import { ChevronsUpDown } from "lucide-react";

export type AgentInfoProps = {
  agent?: Agent | undefined | null;
};

/**
 * WIP
 */
export function AgentInfo({ agent }: AgentInfoProps) {
  if (agent == null) {
    return <div className="w-full h-27" />;
  }

  return (
    <Collapsible className="flex flex-col gap-2">
      <div className="flex items-baseline-last">
        <h2>{agent.name}</h2>
        <CollapsibleTrigger asChild>
          <Button
            variant="ghost"
            size="icon"
            className="size-8 m-2"
          >
            <ChevronsUpDown />
            <span className="sr-only">Details</span>
          </Button>
        </CollapsibleTrigger>
      </div>
      <div>
        {agent.status ?? "Status unknown"}:{" "}
        {agent.status_reason ?? "<no reason>"}
      </div>
      <CollapsibleContent className="flex flex-col gap-2">
        <div className="rounded-md border px-4 py-2 font-mono text-sm">
          {agent.description}
        </div>
        <div className="rounded-md border px-4 py-2 font-mono text-sm">
          ID: {agent.id}
        </div>
        <div className="rounded-md border px-4 py-2 font-mono text-sm">
          ACP Type: {agent.acp_type}
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}
