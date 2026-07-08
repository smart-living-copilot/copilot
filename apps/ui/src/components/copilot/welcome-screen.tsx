'use client';

import type { ReactElement } from 'react';

export interface WelcomeScreenProps {
  historyLoaded?: boolean;
  input?: ReactElement;
  suggestionView?: ReactElement;
}

export function WelcomeScreen({
  historyLoaded = true,
  input,
  suggestionView,
}: WelcomeScreenProps) {
  if (!historyLoaded) {
    return (
      <div className="flex min-h-0 flex-1 items-center justify-center px-4">
        <div className="text-sm text-muted-foreground">Loading chat...</div>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center justify-center space-y-10 p-4 pt-12 md:p-8 md:pt-16 text-center animate-in fade-in slide-in-from-bottom-4 duration-700">
      <div className="flex flex-col items-center space-y-4">
        <div className="space-y-2">
          <h1 className="text-3xl font-bold tracking-tight bg-gradient-to-br from-foreground to-foreground/70 bg-clip-text text-transparent">
            WoTBot
          </h1>
          <p className="text-muted-foreground text-lg max-w-md mx-auto leading-relaxed">
            Your intelligent assistant for managing your smart home. Ask me
            anything about your devices!
          </p>
        </div>
      </div>

      {input ? <div className="w-full max-w-3xl">{input}</div> : null}
      {suggestionView ? (
        <div className="w-full max-w-3xl">{suggestionView}</div>
      ) : null}
    </div>
  );
}
