'use client';

export interface WelcomeScreenProps {
  historyLoaded?: boolean;
}

export function WelcomeScreen({ historyLoaded = true }: WelcomeScreenProps) {
  if (!historyLoaded) {
    return (
      <div className="flex min-h-0 flex-1 items-center justify-center px-4">
        <div className="text-sm text-muted-foreground">Loading chat...</div>
      </div>
    );
  }

  return (
    <div className="pointer-events-none absolute inset-0 flex items-center justify-center px-6 pb-48 text-center animate-in fade-in slide-in-from-bottom-2 duration-500 md:pb-52">
      <h1 className="text-3xl font-semibold tracking-tight text-foreground md:text-4xl">
        How can I help today?
      </h1>
    </div>
  );
}
