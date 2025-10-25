'use client';

import { useEffect, useState } from 'react';

import { Sun, Moon } from 'lucide-react';
import { useTheme } from 'next-themes';

import { IconButton } from '@/components/agentex/icon-button';

export function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  if (!mounted) {
    return null;
  }

  const toggleTheme = () => {
    setTheme(theme === 'light' ? 'dark' : 'light');
  };

  return (
    <IconButton
      variant="ghost"
      onClick={toggleTheme}
      aria-label="Toggle theme"
      icon={theme === 'light' ? Moon : Sun}
    />
  );
}
