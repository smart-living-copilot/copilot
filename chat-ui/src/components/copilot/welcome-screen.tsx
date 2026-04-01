'use client';

import type { ReactElement, ReactNode } from 'react';
import { useAgent } from '@copilotkit/react-core/v2';
import { MessageSquare } from 'lucide-react';
import { Button } from '@/components/ui/button';

export interface ExamplePrompt {
  label: string;
  prompt: string;
  icon?: ReactNode;
}

export interface WelcomeScreenProps {
  examplePrompts?: ExamplePrompt[];
  historyLoaded?: boolean;
  input?: ReactElement;
  suggestionView?: ReactElement;
}

export function WelcomeScreen({
  examplePrompts = [],
  historyLoaded = true,
  input,
  suggestionView,
}: WelcomeScreenProps) {
  const { agent } = useAgent({ agentId: 'copilot' });

  const handlePromptClick = (prompt: string) => {
    agent.addMessage({
      id: window.crypto.randomUUID(),
      role: 'user',
      content: prompt,
    });
    void agent.runAgent();
  };

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
            Smart Living Copilot
          </h1>
          <p className="text-muted-foreground text-lg max-w-md mx-auto leading-relaxed">
            Your intelligent assistant for managing your smart home. Ask me
            anything about your devices!
          </p>
        </div>
      </div>

      {examplePrompts.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 w-full max-w-2xl">
          <div className="md:col-span-2 flex items-center justify-center space-x-2 text-sm font-medium text-muted-foreground/60 mb-1">
            <MessageSquare className="size-4" />
            <span>Try asking...</span>
          </div>
          {examplePrompts.map((item, index) => (
            <Button
              key={index}
              variant="outline"
              className="flex items-center justify-start h-auto p-4 space-x-3 text-left hover:bg-primary/[0.03] hover:border-primary/30 transition-all group border-muted-foreground/10 bg-background/50 backdrop-blur-sm"
              onClick={() => handlePromptClick(item.prompt)}
            >
              {item.icon && (
                <div className="rounded-full bg-muted p-2 group-hover:bg-primary/10 group-hover:text-primary transition-colors shrink-0">
                  {item.icon}
                </div>
              )}
              <div className="flex flex-col overflow-hidden">
                <span className="font-semibold text-sm group-hover:text-primary transition-colors">
                  {item.label}
                </span>
                <span className="text-xs text-muted-foreground truncate group-hover:text-muted-foreground/80 transition-colors">
                  {item.prompt}
                </span>
              </div>
            </Button>
          ))}
        </div>
      )}

      {input ? <div className="w-full max-w-3xl">{input}</div> : null}
      {suggestionView ? (
        <div className="w-full max-w-3xl">{suggestionView}</div>
      ) : null}
    </div>
  );
}
