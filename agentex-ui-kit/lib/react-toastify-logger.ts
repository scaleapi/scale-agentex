import type AgentexSDK from "agentex";
import { toast } from "react-toastify";

export function createReactToastifyLogger(
  toastLevel: Exclude<AgentexSDK["logLevel"], undefined>
): Exclude<AgentexSDK["logger"], undefined> {
  const isDebugToasted = toastLevel === "debug";
  const isInfoToasted = isDebugToasted || toastLevel === "info";
  const isWarnToasted = isInfoToasted || toastLevel === "warn";
  const isErrorToasted = isWarnToasted || toastLevel === "error";

  if (!isErrorToasted) {
    toastLevel satisfies "off";
  }

  return {
    debug: (message, ...rest) => {
      console.debug(message, ...rest);
      if (isDebugToasted) {
        toast.info(message, { autoClose: false });
      }
    },
    error: (message, ...rest) => {
      console.error(message, ...rest);
      if (isErrorToasted) {
        toast.error(message, { autoClose: false });
      }
    },
    info: (message, ...rest) => {
      console.info(message, ...rest);
      if (isInfoToasted) {
        toast.info(message, { autoClose: false });
      }
    },
    warn: (message, ...rest) => {
      console.warn(message, ...rest);
      if (isWarnToasted) {
        toast.warn(message, { autoClose: false });
      }
    },
  };
}
