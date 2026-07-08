import { Geist, Geist_Mono } from 'next/font/google';

import { SessionProvider } from 'next-auth/react';

import { QueryProvider, ThemeProvider } from '@/components/providers';
import { SessionGuard } from '@/components/session-guard';

import type { Metadata } from 'next';
import '@/app/globals.css';

const geistSans = Geist({
  variable: '--font-geist-sans',
  subsets: ['latin'],
});

const geistMono = Geist_Mono({
  variable: '--font-geist-mono',
  subsets: ['latin'],
});

export const metadata: Metadata = {
  title: 'Agentex',
  description: 'Scale Agents',
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  // Gate NextAuth's SessionProvider on auth: in direct (legacy) mode it never
  // mounts, so the client makes no /api/auth/session calls.
  const authEnabled = !!process.env.AGENTEX_UI_AUTH_PROVIDER_ID;
  const tree = (
    <QueryProvider>
      <ThemeProvider
        attribute="class"
        defaultTheme="light"
        enableSystem={false}
        disableTransitionOnChange
      >
        {children}
      </ThemeProvider>
    </QueryProvider>
  );

  return (
    <html lang="en" suppressHydrationWarning>
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased`}
      >
        {authEnabled ? (
          // refetchInterval drives the jwt-callback refresh below the token lifetime so
          // the proxy always reads a fresh token (it can't refresh on its own).
          <SessionProvider refetchInterval={240}>
            <SessionGuard />
            {tree}
          </SessionProvider>
        ) : (
          tree
        )}
      </body>
    </html>
  );
}
