import {
  SETUP_FORM_DATA_HEADER_NAME,
  SetupFormData,
  SetupFormDataSchema,
} from "@/registry/agentex/agentex-dev-root/lib/agentex-dev-root-setup-form";
import { RequestCookies } from "@edge-runtime/cookies";
import AgentexSDK from "agentex";

function safeParseSetupFormData(
  rawSetupFormData: string | null
):
  | { success: SetupFormData | null; error?: undefined }
  | { success?: undefined; error: unknown } {
  if (!rawSetupFormData) {
    return { success: null };
  }

  try {
    return { success: SetupFormDataSchema.parse(JSON.parse(rawSetupFormData)) };
  } catch (error) {
    return { error };
  }
}

/**
 * Blindly proxying requests like this absolutely should not be done in production. This is for local development only!
 *
 * This function proxies requests from the client through the Next.js server so that we don't have to worry about CORS and such.
 */
export async function handleRequest(
  method: string,
  slug: string[],
  requestHeaders: Headers,
  searchParams: URLSearchParams,
  body: ReadableStream<Uint8Array> | null,
  signal: AbortSignal
): Promise<
  | { response: Response | null; error?: undefined }
  | { error: string; response?: undefined }
> {
  if (process.env.NODE_ENV !== "development") {
    return { response: null };
  }

  const setupFormDataParseResult = safeParseSetupFormData(
    requestHeaders.get(SETUP_FORM_DATA_HEADER_NAME)
  );

  if (setupFormDataParseResult.success === undefined) {
    console.error(setupFormDataParseResult.error);
    return { error: `Invalid header value for ${SETUP_FORM_DATA_HEADER_NAME}` };
  }

  const { success: setupFormData } = setupFormDataParseResult;
  const baseURL =
    setupFormData?.baseURL ||
    new AgentexSDK({ environment: "development" }).baseURL;
  const defaultHeaders = setupFormData?.defaultHeaders ?? [];
  const formCookies = setupFormData?.cookies ?? [];
  const apiKey = setupFormData?.apiKeyEnvVar
    ? process.env[setupFormData.apiKeyEnvVar]
    : undefined;

  // CREATE HEADERS
  const headers = new Headers(requestHeaders);

  // Merge headers from client request with form-specified defaults
  // Form does not override existing
  for (const defaultHeader of defaultHeaders.filter(
    (defaultHeader) => !headers.get(defaultHeader.key)
  )) {
    const headerValue = defaultHeader.fromEnv
      ? process.env[defaultHeader.value]
      : defaultHeader.value;
    if (headerValue !== undefined) {
      headers.set(defaultHeader.key, headerValue);
    }
  }

  // Set API key if specified
  // Form overrides existing
  if (apiKey !== undefined) {
    headers.set("authorization", `Bearer ${apiKey}`);
  }

  // Merge client cookies with form-specified cookies
  // Form overrides existing
  const cookies = new RequestCookies(new Headers(headers));
  for (const cookie of formCookies) {
    if (cookie.name && cookie.value) {
      cookies.set(cookie.name, cookie.value);
    }
  }
  if (cookies.size > 0) {
    headers.set("cookie", cookies.toString());
  }
  // END CREATE HEADERS

  const proxyURL = new URL(`${baseURL}/${slug.join("/")}`);
  proxyURL.search = searchParams.toString();

  const response = await fetch(proxyURL, {
    method,
    headers,
    body,
    signal,
    ...(body !== null ? { duplex: "half" } : null),
  });

  return { response };
}
