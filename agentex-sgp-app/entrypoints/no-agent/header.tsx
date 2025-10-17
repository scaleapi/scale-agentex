import { BackToSGPLink } from '@/components/agentex/back-to-sgp-link';
import { ThemeToggle } from '@/components/agentex/theme-toggle';
import { memo } from 'react';

function HeaderImpl() {
  return (
    <header className="w-full md:sticky mt-4 md:top-0 md:z-10 bg-background">
      <div className="mx-auto max-w-[min(100%-var(--spacing)*4,var(--max-page-content-width))] xl:max-w-[min(100%-var(--spacing)*4,var(--max-page-content-width)+var(--spacing)*52)]">
        <div className="flex flex-col justify-center xl:flex-row xl:items-center-safe xl:justify-between gap-2 mx-4 xl:mr-26 my-2">
          <div className="flex items-baseline-last justify-center-safe gap-2">
            <BackToSGPLink className="hidden xl:inline" />
            <h1>Agentex</h1>
          </div>
          <div className="flex justify-between items-end-safe">
            <BackToSGPLink className="xl:hidden" />
            <ThemeToggle />
          </div>
        </div>
      </div>
    </header>
  );
}

export const Header = memo(HeaderImpl);
