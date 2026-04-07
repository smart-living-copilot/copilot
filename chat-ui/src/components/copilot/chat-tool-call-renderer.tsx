'use client';

import { defineToolCallRenderer } from '@copilotkit/react-core/v2';

import { GenericToolCallCard, RunCodeCard } from './chat-tool-call-cards';
import { type CatchAllToolCallRenderProps } from './chat-tool-call-model';

export const chatToolCallRenderers = [
  defineToolCallRenderer({
    name: '*',
    render: (props: CatchAllToolCallRenderProps) => {
      if (props.name === 'run_code') {
        return <RunCodeCard {...props} />;
      }

      return <GenericToolCallCard {...props} />;
    },
  }),
];
