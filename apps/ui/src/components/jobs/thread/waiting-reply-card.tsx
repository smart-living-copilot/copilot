import { type FormEvent } from 'react';
import Link from 'next/link';
import { Eye, Send } from 'lucide-react';

import {
  ReadAloudButton,
  VoiceAnswerButton,
} from '@/components/jobs/job-speech-controls';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Spinner } from '@/components/ui/spinner';
import { Textarea } from '@/components/ui/textarea';

interface WaitingReplyCardProps {
  question: string;
  value: string;
  isSubmitting: boolean;
  detailsHref: string;
  onChange: (value: string) => void;
  onVoiceAnswer: (value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}

export function WaitingReplyCard({
  question,
  value,
  isSubmitting,
  detailsHref,
  onChange,
  onVoiceAnswer,
  onSubmit,
}: WaitingReplyCardProps) {
  const canSubmit = value.trim().length > 0 && !isSubmitting;

  return (
    <Card className="rounded-md border-border/70 shadow-sm shadow-black/5">
      <CardContent className="space-y-4">
        <div className="space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-lg font-semibold tracking-tight">
              Waiting for input
            </h2>
            <Badge variant="secondary">Needs input</Badge>
          </div>
          <p className="text-sm text-muted-foreground">
            This job is paused until you answer its pending question.
          </p>
        </div>
        <div className="rounded-md border bg-muted/20 p-4">
          <div className="flex items-center justify-between gap-3">
            <div className="text-xs font-medium text-muted-foreground">
              Question
            </div>
            <ReadAloudButton text={question} compact />
          </div>
          <p className="mt-2 whitespace-pre-wrap break-words text-base leading-7 text-foreground">
            {question}
          </p>
        </div>
        <form className="space-y-3" onSubmit={onSubmit}>
          <Textarea
            aria-label="Job answer"
            className="min-h-28 resize-y"
            placeholder="Answer..."
            value={value}
            onChange={(event) => onChange(event.target.value)}
            disabled={isSubmitting}
          />
          <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
            <Button variant="outline" asChild>
              <Link href={detailsHref}>
                <Eye className="h-4 w-4" />
                Details
              </Link>
            </Button>
            <VoiceAnswerButton
              disabled={isSubmitting}
              onTranscript={onVoiceAnswer}
            />
            <Button type="submit" disabled={!canSubmit}>
              {isSubmitting ? (
                <Spinner className="size-4" />
              ) : (
                <Send className="h-4 w-4" />
              )}
              Submit answer
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
