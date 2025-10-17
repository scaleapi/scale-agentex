import { handleRequest } from "@/registry/agentex/agentex-dev-root/api/agentex/[...slug]/handlers";

describe("/api/agentex handlers", () => {
  it("GET should not return a response outside of development", async () => {
    const { response } = await handleRequest(
      "GET",
      [],
      new Headers(),
      new URLSearchParams(),
      null,
      new AbortController().signal
    );
    expect(response).toBeNull();
  });

  it("POST should not return a response outside of development", async () => {
    const { response } = await handleRequest(
      "POST",
      [],
      new Headers(),
      new URLSearchParams(),
      null,
      new AbortController().signal
    );
    expect(response).toBeNull();
  });
});
