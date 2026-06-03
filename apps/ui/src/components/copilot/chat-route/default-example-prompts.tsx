import { useMemo } from 'react';
import { Activity, Cloud, Thermometer, TrendingUp } from 'lucide-react';

import { type ExamplePrompt } from '@/components/copilot/welcome-screen';

export function useDefaultExamplePrompts(): ExamplePrompt[] {
  return useMemo(
    () => [
      {
        label: 'Kitchen temperature',
        prompt: 'Show me the current temperature in the kitchen',
        icon: <Thermometer className="size-4" />,
      },
      {
        label: 'Motion heatmap',
        prompt:
          'Create an hourly heatmap per room for the motion data of the last 24 hours',
        icon: <Activity className="size-4" />,
      },
      {
        label: 'Energy comparison',
        prompt:
          'Show the energy consumption of all households for the last 12 hours and compare them',
        icon: <TrendingUp className="size-4" />,
      },
      {
        label: 'CO2 forecast',
        prompt:
          'Create a forecast for the CO2 sensors for tomorrow for all rooms',
        icon: <Cloud className="size-4" />,
      },
    ],
    [],
  );
}
