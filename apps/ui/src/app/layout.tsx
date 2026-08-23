import type { Metadata } from 'next';
import { Geist, Geist_Mono } from 'next/font/google';
import './globals.css';
import { PANEL_HOST_TEMPLATE_ATTRIBUTE } from '@/lib/panel-origin';
import { Providers } from './providers';

const geistSans = Geist({
  variable: '--font-geist-sans',
  subsets: ['latin'],
});

const geistMono = Geist_Mono({
  variable: '--font-geist-mono',
  subsets: ['latin'],
});

export const metadata: Metadata = {
  title: 'WoTBot',
  description: 'Your intelligent Web of Things assistant',
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    // The panel host template travels on the document rather than in the
    // bundle: it is a deployment setting, and a `NEXT_PUBLIC_` value would be
    // frozen at image build time instead of read from this deployment's env.
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
      suppressHydrationWarning
      {...{
        [PANEL_HOST_TEMPLATE_ATTRIBUTE]: process.env.PANEL_HOST_TEMPLATE || '',
      }}
    >
      <body className="h-full overflow-hidden bg-background text-foreground">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
