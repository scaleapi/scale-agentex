"use client";

import {
  SETUP_FORM_DATA_HEADER_NAME,
  SetupFormData,
  SetupFormDataSchema,
} from "@/registry/agentex/agentex-dev-root/lib/agentex-dev-root-setup-form";
import AgentexSDK from "agentex";
import { createContext, useContext } from "react";
import { createStore, StoreApi, useStore } from "zustand";

function createClientFromFormData(
  data: SetupFormData,
  clientLocation: Readonly<Pick<Location, "protocol" | "host">>
): AgentexSDK {
  return new AgentexSDK({
    baseURL:
      clientLocation.protocol + "//" + clientLocation.host + "/api/agentex",
    maxRetries: data.maxRetries,
    timeout: data.timeout,
    defaultHeaders: {
      [SETUP_FORM_DATA_HEADER_NAME]: JSON.stringify(data),
    },
  });
}

const getSetupFormDataFromStorage = (
  storage: Storage,
  storageKey: string
): SetupFormData | null => {
  const storedParams = storage.getItem(storageKey);
  if (storedParams !== null) {
    const parseResult = SetupFormDataSchema.safeParse(JSON.parse(storedParams));
    if (parseResult.success) {
      return parseResult.data;
    }
  }
  return null;
};

type AgentexDevRootSetupStoreProps = {
  storageKey: string;
};

type AgentexDevRootSetupStoreState = AgentexDevRootSetupStoreProps & {
  client: AgentexSDK;
  setupFormDefaultValues: SetupFormData;
  isSetupFormOpen: boolean;
  setIsSetupFormOpen: (open: boolean) => void;
  setupFormOnSubmit: (data: SetupFormData) => void;
};

type AgentexDevRootSetupStore = StoreApi<AgentexDevRootSetupStoreState>;

function getStorage(): Storage | null {
  return typeof window !== "undefined" ? window.localStorage : null;
}

function createAgentexDevRootSetupStore(
  initialState: AgentexDevRootSetupStoreProps,
  clientLocation: Readonly<Pick<Location, "protocol" | "host">>
): AgentexDevRootSetupStore {
  const initialStorage = getStorage();
  const formDataFromStorage =
    initialStorage !== null
      ? getSetupFormDataFromStorage(initialStorage, initialState.storageKey)
      : null;

  const calculatedFormData: SetupFormData = formDataFromStorage ?? {
    baseURL: "",
    apiKeyEnvVar: "",
    defaultHeaders: [],
    cookies: [],
    maxRetries: 3,
    timeout: 300_000,
  };

  if (formDataFromStorage === null) {
    // make sure we only default to open once
    initialStorage?.setItem(
      initialState.storageKey,
      JSON.stringify(calculatedFormData)
    );
  }

  return createStore((set) => ({
    ...initialState,
    client: createClientFromFormData(calculatedFormData, clientLocation),
    setupFormDefaultValues: calculatedFormData,
    isSetupFormOpen: formDataFromStorage === null, // default open if nothing was found in storage
    setIsSetupFormOpen: (open) => set({ isSetupFormOpen: open }),
    setupFormOnSubmit: (data) => {
      const client = createClientFromFormData(data, clientLocation);
      set({
        client,
        setupFormDefaultValues: data,
        isSetupFormOpen: false,
      });
      getStorage()?.setItem(initialState.storageKey, JSON.stringify(data));
    },
  }));
}

const AgentexDevRootSetupStoreContext =
  createContext<AgentexDevRootSetupStore | null>(null);

function useAgentexDevRootSetupStore<T>(
  selector: (state: AgentexDevRootSetupStoreState) => T
): T {
  const store = useContext(AgentexDevRootSetupStoreContext);
  if (store === null) {
    throw new Error(
      "useAgentexDevRootSetupStore must be used within AgentexDevRootSetupStoreContext"
    );
  }
  return useStore(store, selector);
}

export {
  AgentexDevRootSetupStoreContext,
  createAgentexDevRootSetupStore,
  useAgentexDevRootSetupStore,
};
export type { AgentexDevRootSetupStore };
