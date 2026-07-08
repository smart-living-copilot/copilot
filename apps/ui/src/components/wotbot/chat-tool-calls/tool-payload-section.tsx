import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

import { formatToolData, hasInspectableData } from '../chat-tool-call-model';

export function ToolPayloadSection({
  title,
  value,
}: {
  title: string;
  value: unknown;
}) {
  if (!hasInspectableData(value)) {
    return null;
  }

  return (
    <Card className="gap-0 border border-border/60 bg-background/80 py-0 shadow-none ring-0">
      <CardHeader className="border-b border-border/60 py-2">
        <CardTitle className="text-[0.66rem] font-semibold tracking-[0.16em] text-muted-foreground uppercase">
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent className="py-2.5">
        <pre className="max-h-60 overflow-auto text-[0.74rem] leading-5 whitespace-pre-wrap text-foreground">
          {formatToolData(value)}
        </pre>
      </CardContent>
    </Card>
  );
}
