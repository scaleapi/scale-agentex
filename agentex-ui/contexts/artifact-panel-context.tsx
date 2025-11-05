'use client';

import React, {
  createContext,
  useContext,
  useState,
  ReactNode,
  useMemo,
  useCallback,
} from 'react';

import type { MapMetadata } from '@/lib/types';

type ArtifactPanelState = {
  isOpen: boolean;
  pdfUrl: string | null;
  eventTitle: string | null;
  mapAddress: string | null;
  mapMetadata: MapMetadata | null;
  taskId: string | null;
};

type ArtifactPanelActions = {
  openPdf: (url: string, title: string) => void;
  openMap: (address: string, title: string, metadata?: MapMetadata) => void;
  openDataTables: (taskId: string, title: string) => void;
  closeArtifact: () => void;
};

const ArtifactPanelStateContext = createContext<ArtifactPanelState | undefined>(
  undefined
);

const ArtifactPanelActionsContext = createContext<
  ArtifactPanelActions | undefined
>(undefined);

export function ArtifactPanelProvider({ children }: { children: ReactNode }) {
  const [isOpen, setIsOpen] = useState(false);
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [mapAddress, setMapAddress] = useState<string | null>(null);
  const [mapMetadata, setMapMetadata] = useState<MapMetadata | null>(null);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [eventTitle, setEventTitle] = useState<string | null>(null);

  const state = useMemo<ArtifactPanelState>(
    () => ({
      isOpen,
      pdfUrl,
      eventTitle,
      mapAddress,
      mapMetadata,
      taskId,
    }),
    [isOpen, pdfUrl, eventTitle, mapAddress, mapMetadata, taskId]
  );

  const openPdf = useCallback((url: string, title: string) => {
    setPdfUrl(url);
    setMapAddress(null);
    setMapMetadata(null);
    setTaskId(null);
    setEventTitle(title);
    setIsOpen(true);
  }, []);

  const openMap = useCallback(
    (address: string, title: string, metadata?: MapMetadata) => {
      setMapAddress(address);
      setMapMetadata(metadata || null);
      setPdfUrl(null);
      setTaskId(null);
      setEventTitle(title);
      setIsOpen(true);
    },
    []
  );

  const openDataTables = useCallback((taskId: string, title: string) => {
    setTaskId(taskId);
    setPdfUrl(null);
    setMapAddress(null);
    setEventTitle(title);
    setIsOpen(true);
  }, []);

  const closeArtifact = useCallback(() => {
    setIsOpen(false);
    setTimeout(() => {
      setPdfUrl(null);
      setMapAddress(null);
      setMapMetadata(null);
      setTaskId(null);
      setEventTitle(null);
    }, 300);
  }, []);

  const actions = useMemo<ArtifactPanelActions>(
    () => ({
      openPdf,
      openMap,
      openDataTables,
      closeArtifact,
    }),
    [openPdf, openMap, openDataTables, closeArtifact]
  );

  return (
    <ArtifactPanelStateContext.Provider value={state}>
      <ArtifactPanelActionsContext.Provider value={actions}>
        {children}
      </ArtifactPanelActionsContext.Provider>
    </ArtifactPanelStateContext.Provider>
  );
}

export function useArtifactPanelState() {
  const context = useContext(ArtifactPanelStateContext);
  if (context === undefined) {
    throw new Error(
      'useArtifactPanelState must be used within an ArtifactPanelProvider'
    );
  }
  return context;
}

export function useArtifactPanelActions() {
  const context = useContext(ArtifactPanelActionsContext);
  if (context === undefined) {
    throw new Error(
      'useArtifactPanelActions must be used within an ArtifactPanelProvider'
    );
  }
  return context;
}

export function useArtifactPanel() {
  return {
    ...useArtifactPanelState(),
    ...useArtifactPanelActions(),
  };
}
