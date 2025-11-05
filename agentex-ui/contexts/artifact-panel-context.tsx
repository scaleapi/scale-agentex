'use client';

import React, { createContext, useContext, useState, ReactNode } from 'react';

interface ArtifactPanelContextType {
  isOpen: boolean;
  url: string | null;
  eventTitle: string | null;
  openArtifact: (url: string, title: string) => void;
  closeArtifact: () => void;
}

const ArtifactPanelContext = createContext<
  ArtifactPanelContextType | undefined
>(undefined);

export function ArtifactPanelProvider({ children }: { children: ReactNode }) {
  const [isOpen, setIsOpen] = useState(false);
  const [url, setUrl] = useState<string | null>(null);
  const [eventTitle, setEventTitle] = useState<string | null>(null);

  const openArtifact = (url: string, title: string) => {
    setUrl(url);
    setEventTitle(title);
    setIsOpen(true);
  };

  const closeArtifact = () => {
    setIsOpen(false);
    setTimeout(() => {
      setUrl(null);
      setEventTitle(null);
    }, 300);
  };

  return (
    <ArtifactPanelContext.Provider
      value={{ isOpen, url, eventTitle, openArtifact, closeArtifact }}
    >
      {children}
    </ArtifactPanelContext.Provider>
  );
}

export function useArtifactPanel() {
  const context = useContext(ArtifactPanelContext);
  if (context === undefined) {
    throw new Error(
      'useArtifactPanel must be used within an ArtifactPanelProvider'
    );
  }
  return context;
}
