'use client';

import { useCopilotAction } from '@copilotkit/react-core';

import { GenericToolCallCard, RunCodeCard } from './chat-tool-call-cards';
import { type CatchAllToolCallRenderProps } from './chat-tool-call-model';

export function ChatToolCallRenderer() {
  useCopilotAction(
    {
      name: '*',
      render: (props: CatchAllToolCallRenderProps) => {
        if (props.name === 'run_code') {
          return <RunCodeCard {...props} />;
        }

        return <GenericToolCallCard {...props} />;
      },
    },
    [],
  );

  return null;
}
