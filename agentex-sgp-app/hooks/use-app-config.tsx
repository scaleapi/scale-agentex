import { createContext, useContext } from 'react';

type AppConfig = {
  sgpAppURL: string;
  agentexAPIBaseURL: string;
};

const AppConfigContext = createContext<AppConfig | null>(null);

function useAppConfig(): AppConfig {
  const appConfig = useContext(AppConfigContext);
  if (!appConfig) {
    throw new Error('useAppConfig must be used within an AppConfigProvider');
  }
  return appConfig;
}

function AppConfigProvider({
  sgpAppURL,
  agentexAPIBaseURL,
  children,
}: {
  sgpAppURL: string;
  agentexAPIBaseURL: string;
  children?: React.ReactNode;
}) {
  return (
    <AppConfigContext.Provider value={{ sgpAppURL, agentexAPIBaseURL }}>
      {children}
    </AppConfigContext.Provider>
  );
}

export { AppConfigProvider, useAppConfig };
