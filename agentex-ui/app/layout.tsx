import { Geist, Geist_Mono } from 'next/font/google';

import { QueryProvider, ThemeProvider } from '@/components/providers';
import { ArtifactPanelProvider } from '@/contexts/artifact-panel-context';

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
  return (
    <html lang="en" suppressHydrationWarning>
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased`}
      >
        <QueryProvider>
          <ThemeProvider
            attribute="class"
            defaultTheme="light"
            enableSystem={false}
            disableTransitionOnChange
          >
            <ArtifactPanelProvider>{children}</ArtifactPanelProvider>
          </ThemeProvider>
        </QueryProvider>
      </body>
    </html>
  );
}
