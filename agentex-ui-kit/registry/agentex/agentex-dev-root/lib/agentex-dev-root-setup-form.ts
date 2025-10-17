import z from "zod";

/**
 * Used to by the agentex API proxy to get setup form data stored by the client to the server making the actual request.
 */
const SETUP_FORM_DATA_HEADER_NAME = "x-agentex-ui-kit-setup-form-data" as const;

const SetupFormDataSchema = z.object({
  baseURL: z.union([z.url(), z.literal("")]),
  apiKeyEnvVar: z.string(),
  defaultHeaders: z.array(
    z.object({ key: z.string(), value: z.string(), fromEnv: z.boolean() })
  ),
  cookies: z.array(
    z.object({ name: z.string(), value: z.string() })
  ),
  maxRetries: z.number().int().min(0),
  timeout: z.number().int().min(0),
});

type SetupFormData = z.infer<typeof SetupFormDataSchema>;

export { SETUP_FORM_DATA_HEADER_NAME, SetupFormDataSchema };
export type { SetupFormData };
