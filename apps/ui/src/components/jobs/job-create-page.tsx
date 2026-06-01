'use client';

import { FormEvent, useCallback, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Loader2, Plus } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Textarea } from '@/components/ui/textarea';
import { type CreateJobPayload, createJob } from '@/lib/jobs-api';

type CreateJobFormState = {
  name: string;
  threadId: string;
  actionKind: 'prompt' | 'analysis';
  triggerKind: 'time' | 'event';
  scheduleKind: 'once' | 'interval';
  prompt: string;
  analysisCode: string;
  intervalSeconds: string;
  runAt: string;
  thingId: string;
  eventName: string;
  subscriptionInput: string;
};

const INITIAL_CREATE_FORM: CreateJobFormState = {
  name: '',
  threadId: '',
  actionKind: 'prompt',
  triggerKind: 'time',
  scheduleKind: 'interval',
  prompt: '',
  analysisCode: '',
  intervalSeconds: '',
  runAt: '',
  thingId: '',
  eventName: '',
  subscriptionInput: '',
};

function toCreatePayload(form: CreateJobFormState): CreateJobPayload {
  const payload: CreateJobPayload = {
    name: form.name.trim(),
    created_from_thread_id: form.threadId.trim(),
    action_kind: form.actionKind,
    trigger_kind: form.triggerKind,
  };

  if (form.actionKind === 'analysis') {
    payload.analysis_code = form.analysisCode.trim();
  } else {
    payload.prompt = form.prompt.trim();
  }

  if (payload.trigger_kind === 'time') {
    payload.schedule_kind = form.scheduleKind;
    if (form.scheduleKind === 'interval' && form.intervalSeconds.trim()) {
      payload.interval_seconds = Number(form.intervalSeconds);
    }
    if (form.scheduleKind === 'once' && form.runAt.trim()) {
      payload.run_at = new Date(form.runAt).toISOString();
    }
  } else {
    payload.thing_id = form.thingId.trim();
    payload.event_name = form.eventName.trim();
    if (form.subscriptionInput.trim()) {
      payload.subscription_input = JSON.parse(form.subscriptionInput);
    }
  }

  return payload;
}

export function JobCreatePage() {
  const router = useRouter();
  const [form, setForm] = useState<CreateJobFormState>(INITIAL_CREATE_FORM);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const setField = useCallback(
    <K extends keyof CreateJobFormState>(
      field: K,
      value: CreateJobFormState[K],
    ) => {
      setForm((current) => ({ ...current, [field]: value }));
    },
    [],
  );

  const handleSubmit = useCallback(
    async (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      setIsSubmitting(true);
      try {
        const job = await createJob(toCreatePayload(form));
        toast.success('Job created.');
        router.push(`/jobs/${job.id}`);
      } catch (error) {
        toast.error(
          error instanceof Error ? error.message : 'Failed to create job',
        );
      } finally {
        setIsSubmitting(false);
      }
    },
    [form, router],
  );

  return (
    <form className="space-y-5" onSubmit={(event) => void handleSubmit(event)}>
      <section className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div className="space-y-1">
          <h1 className="text-3xl font-semibold tracking-tight">Create job</h1>
          <p className="max-w-3xl text-sm text-muted-foreground">
            Define one action and one trigger for a background automation.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button type="button" variant="outline" asChild>
            <Link href="/jobs">Cancel</Link>
          </Button>
          <Button type="submit" disabled={isSubmitting}>
            {isSubmitting ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Plus className="h-4 w-4" />
            )}
            Create
          </Button>
        </div>
      </section>

      <Card className="rounded-md border-border/70 shadow-sm shadow-black/5">
        <CardHeader className="border-b border-border/70">
          <CardTitle className="text-base">Identity</CardTitle>
          <CardDescription>
            Name the job and link it back to the originating chat thread.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-2">
            <label className="text-sm font-medium">Name</label>
            <Input
              value={form.name}
              onChange={(event) => setField('name', event.target.value)}
              placeholder="Morning energy summary"
            />
          </div>
          <div className="space-y-2">
            <label className="text-sm font-medium">Created from thread</label>
            <Input
              value={form.threadId}
              onChange={(event) => setField('threadId', event.target.value)}
              placeholder="chat-thread-123"
            />
          </div>
        </CardContent>
      </Card>

      <Card className="rounded-md border-border/70 shadow-sm shadow-black/5">
        <CardHeader className="border-b border-border/70">
          <CardTitle className="text-base">Action</CardTitle>
          <CardDescription>
            Choose what the job should do each time it runs.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Tabs
            value={form.actionKind}
            onValueChange={(value) =>
              setField('actionKind', value as 'prompt' | 'analysis')
            }
            className="space-y-4"
          >
            <TabsList className="grid w-full grid-cols-2 sm:w-fit">
              <TabsTrigger value="prompt">Prompt</TabsTrigger>
              <TabsTrigger value="analysis">Analysis</TabsTrigger>
            </TabsList>

            <TabsContent value="prompt" className="mt-0">
              <div className="space-y-2">
                <label className="text-sm font-medium">Prompt</label>
                <Textarea
                  rows={9}
                  value={form.prompt}
                  onChange={(event) => setField('prompt', event.target.value)}
                  placeholder="Summarize the latest occupancy and temperature changes."
                />
              </div>
            </TabsContent>

            <TabsContent value="analysis" className="mt-0">
              <div className="space-y-2">
                <label className="text-sm font-medium">Analysis code</label>
                <Textarea
                  rows={12}
                  value={form.analysisCode}
                  onChange={(event) =>
                    setField('analysisCode', event.target.value)
                  }
                  placeholder="print({'summary': '...', 'value': 0.8})"
                />
              </div>
            </TabsContent>
          </Tabs>
        </CardContent>
      </Card>

      <Card className="rounded-md border-border/70 shadow-sm shadow-black/5">
        <CardHeader className="border-b border-border/70">
          <CardTitle className="text-base">Trigger</CardTitle>
          <CardDescription>
            Pick whether this job runs on a schedule or from a Thing event.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Tabs
            value={form.triggerKind}
            onValueChange={(value) =>
              setField('triggerKind', value as 'time' | 'event')
            }
            className="space-y-4"
          >
            <TabsList className="grid w-full grid-cols-2 sm:w-fit">
              <TabsTrigger value="time">Time</TabsTrigger>
              <TabsTrigger value="event">Event</TabsTrigger>
            </TabsList>

            <TabsContent value="time" className="mt-0">
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <label className="text-sm font-medium">Schedule</label>
                  <Select
                    value={form.scheduleKind}
                    onValueChange={(value: 'once' | 'interval') =>
                      setField('scheduleKind', value)
                    }
                  >
                    <SelectTrigger className="w-full">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="interval">Interval</SelectItem>
                      <SelectItem value="once">Once</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium">
                    Interval seconds
                  </label>
                  <Input
                    type="number"
                    min="1"
                    value={form.intervalSeconds}
                    disabled={form.scheduleKind !== 'interval'}
                    onChange={(event) =>
                      setField('intervalSeconds', event.target.value)
                    }
                    placeholder="300"
                  />
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium">Run once at</label>
                  <Input
                    type="datetime-local"
                    value={form.runAt}
                    disabled={form.scheduleKind !== 'once'}
                    onChange={(event) => setField('runAt', event.target.value)}
                  />
                </div>
              </div>
            </TabsContent>

            <TabsContent value="event" className="mt-0">
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <label className="text-sm font-medium">Thing ID</label>
                  <Input
                    value={form.thingId}
                    onChange={(event) =>
                      setField('thingId', event.target.value)
                    }
                    placeholder="urn:dev:ops:thermostat-1"
                  />
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium">Event name</label>
                  <Input
                    value={form.eventName}
                    onChange={(event) =>
                      setField('eventName', event.target.value)
                    }
                    placeholder="overheat"
                  />
                </div>
                <div className="space-y-2 sm:col-span-2">
                  <label className="text-sm font-medium">
                    Subscription input JSON
                  </label>
                  <Textarea
                    rows={5}
                    value={form.subscriptionInput}
                    onChange={(event) =>
                      setField('subscriptionInput', event.target.value)
                    }
                    placeholder='{"threshold": 30}'
                  />
                </div>
              </div>
            </TabsContent>
          </Tabs>
        </CardContent>
      </Card>
    </form>
  );
}
