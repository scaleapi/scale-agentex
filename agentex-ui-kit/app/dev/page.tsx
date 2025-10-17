"use server";

import { AgentexDev } from "@/entrypoints/dev";
import { notFound } from "next/navigation";

export default async function Dev() {
  if (process.env.NODE_ENV !== "development") {
    return notFound();
  }

  return <AgentexDev />;
}
