import { LogOut, MessageSquare } from 'lucide-react';

import { AccountPicker } from '@/components/account-picker/account-picker';
import { useAgentexClient } from '@/components/providers';
import { IconButton } from '@/components/ui/icon-button';
import { ResizableSidebar } from '@/components/ui/resizable-sidebar';
import { cn } from '@/lib/utils';

const FEEDBACK_URL = 'https://github.com/scaleapi/scale-agentex/issues/new';

function openFeedback() {
  window.open(FEEDBACK_URL, '_blank', 'noopener,noreferrer');
}

export type TaskSidebarFooterProps = {
  className?: string;
  collapsed?: boolean;
};

export function TaskSidebarFooter({
  className,
  collapsed = false,
}: TaskSidebarFooterProps) {
  const { authEnabled } = useAgentexClient();

  if (collapsed) {
    return (
      <div className={cn('flex flex-col items-start gap-2 pl-2', className)}>
        <IconButton
          icon={MessageSquare}
          onClick={openFeedback}
          variant="ghost"
          className="text-foreground"
          aria-label="Give Feedback"
        />
        <AccountPicker collapsed />
        {authEnabled && <LogoutButton collapsed />}
      </div>
    );
  }

  return (
    <div className={cn('mx-2 mb-2 flex flex-col gap-2', className)}>
      <ResizableSidebar.Button
        onClick={openFeedback}
        className="flex items-center gap-2 p-2"
        disableAnimation
      >
        <div className="flex items-center gap-2">
          <MessageSquare className="size-5" />
          Give Feedback
        </div>
      </ResizableSidebar.Button>
      <AccountPicker />
      {authEnabled && <LogoutButton />}
    </div>
  );
}

// Rendered only when auth is enabled (gated by the footer). When it is, the middleware
// guarantees an authenticated session, so this always shows — no session check, which
// would otherwise flicker in after the async session resolves.
function LogoutButton({ collapsed = false }: { collapsed?: boolean }) {
  const handleLogout = () => {
    window.location.href = '/api/auth/logout';
  };

  if (collapsed) {
    return (
      <IconButton
        icon={LogOut}
        onClick={handleLogout}
        variant="ghost"
        className="text-foreground"
        aria-label="Log out"
      />
    );
  }

  return (
    <ResizableSidebar.Button
      onClick={handleLogout}
      className="flex items-center gap-2 p-2"
      disableAnimation
    >
      <div className="flex items-center gap-2">
        <LogOut className="size-5" />
        Log out
      </div>
    </ResizableSidebar.Button>
  );
}
