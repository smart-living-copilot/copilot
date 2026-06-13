'use client';

import { type ReactNode } from 'react';
import Link from 'next/link';
import {
  Check,
  ChevronRight,
  Lock,
  Play,
  Shield,
  Trash2,
  X,
} from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { cn } from '@/lib/utils';
import { type RuntimeAffordanceType } from '@/lib/wot-runtime-api';
import { type VirtualThingBinding } from '@/lib/virtual-things-api';

import {
  type ActionDef,
  type EventDef,
  type PropertyDef,
  type SecurityDefinition,
  type StoredCredential,
} from './thing-detail-model';

/**
 * Per-row Run / Binding controls.
 * - `onRun` runs the affordance (a dialog) — available in every context.
 * - `onOpenBinding` opens the binding editor in place (full details page).
 * - `bindingHref` deep-links to the full page (compact drawer context).
 * Pass one of `onOpenBinding` / `bindingHref`, not both.
 */
export interface RowActionsProps {
  bindings?: Map<string, VirtualThingBinding>;
  onRun?: (affordanceType: RuntimeAffordanceType, name: string) => void;
  runRequiresBinding?: boolean;
  onOpenBinding?: (key: string) => void;
  bindingHref?: (key: string) => string;
  /** Binding key whose row is currently selected/open in the editor. */
  activeKey?: string | null;
}

function isActiveRow(
  activeKey: string | null | undefined,
  affordanceType: RuntimeAffordanceType,
  name: string,
) {
  return activeKey === `${affordanceType}:${name}`;
}

function hasRowActions({
  bindings,
  onRun,
  runRequiresBinding,
  onOpenBinding,
  bindingHref,
}: RowActionsProps) {
  const canRun = Boolean(onRun && (!runRequiresBinding || bindings));
  const canOpenBinding = Boolean(bindings && (onOpenBinding || bindingHref));
  return canRun || canOpenBinding;
}

function RowActionsHeadCell({ show }: { show: boolean }) {
  return show ? (
    <TableHead className="w-px text-right">Actions</TableHead>
  ) : null;
}

function RowActionsCell({
  affordanceType,
  name,
  bindings,
  onRun,
  runRequiresBinding,
  onOpenBinding,
  bindingHref,
}: RowActionsProps & {
  affordanceType: RuntimeAffordanceType;
  name: string;
}) {
  if (
    !hasRowActions({
      bindings,
      onRun,
      runRequiresBinding,
      onOpenBinding,
      bindingHref,
    })
  ) {
    return null;
  }
  const key = `${affordanceType}:${name}`;
  const runnable = runRequiresBinding ? (bindings?.has(key) ?? false) : true;
  const hasBinding = bindings?.has(key) ?? false;
  return (
    <TableCell className="text-right">
      <div className="flex items-center justify-end gap-1">
        {onRun && runnable ? (
          <Button
            size="sm"
            variant="ghost"
            onClick={() => onRun(affordanceType, name)}
          >
            <Play className="h-3.5 w-3.5" />
            Run
          </Button>
        ) : null}
        {hasBinding && onOpenBinding ? (
          <Button
            size="sm"
            variant="ghost"
            className="-mr-2"
            onClick={() => onOpenBinding(key)}
          >
            Binding
            <ChevronRight className="h-3.5 w-3.5" />
          </Button>
        ) : hasBinding && bindingHref ? (
          <Button size="sm" variant="ghost" className="-mr-2" asChild>
            <Link href={bindingHref(key)}>
              Binding
              <ChevronRight className="h-3.5 w-3.5" />
            </Link>
          </Button>
        ) : null}
      </div>
    </TableCell>
  );
}

function ThingSectionCard({
  title,
  description,
  children,
}: {
  title: ReactNode;
  description: ReactNode;
  children: ReactNode;
}) {
  return (
    <Card className="rounded-md border-border/70 shadow-sm shadow-black/5">
      <CardHeader>
        <CardTitle className="text-base">{title}</CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}

function TableShell({ children }: { children: ReactNode }) {
  return <div className="rounded-md border border-border/70">{children}</div>;
}

function EmptyState({ children }: { children: ReactNode }) {
  return <p className="text-sm text-muted-foreground">{children}</p>;
}

function NameCell({ value }: { value: string }) {
  return <TableCell className="font-mono text-xs">{value}</TableCell>;
}

function SchemaBadge({ value }: { value?: string }) {
  return <Badge variant="outline">{value ?? '-'}</Badge>;
}

function BooleanStateIcon({ value }: { value?: boolean }) {
  return value ? (
    <Check className="h-4 w-4 text-green-600" />
  ) : (
    <X className="h-4 w-4 text-muted-foreground/40" />
  );
}

export function ThingPropertiesSection({
  properties,
  bindings,
  onRun,
  runRequiresBinding,
  onOpenBinding,
  bindingHref,
  activeKey,
}: {
  properties: PropertyDef[];
} & RowActionsProps) {
  const showActions = hasRowActions({
    bindings,
    onRun,
    runRequiresBinding,
    onOpenBinding,
    bindingHref,
  });
  return (
    <ThingSectionCard
      title="Properties"
      description={
        <>
          {properties.length} propert{properties.length === 1 ? 'y' : 'ies'}{' '}
          defined in this Thing Description.
        </>
      }
    >
      {properties.length > 0 ? (
        <TableShell>
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>Name</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>ReadOnly</TableHead>
                <TableHead>Observable</TableHead>
                <TableHead>Unit</TableHead>
                <TableHead>Description</TableHead>
                <RowActionsHeadCell show={showActions} />
              </TableRow>
            </TableHeader>
            <TableBody>
              {properties.map((property) => (
                <TableRow
                  key={property.name}
                  className={cn(
                    isActiveRow(activeKey, 'property', property.name) &&
                      'bg-primary/5',
                  )}
                >
                  <NameCell value={property.name} />
                  <TableCell>
                    <SchemaBadge value={property.type} />
                  </TableCell>
                  <TableCell>
                    <BooleanStateIcon value={property.readOnly} />
                  </TableCell>
                  <TableCell>
                    <BooleanStateIcon value={property.observable} />
                  </TableCell>
                  <TableCell>{property.unit ?? '-'}</TableCell>
                  <TableCell className="text-muted-foreground">
                    {property.description ?? '-'}
                  </TableCell>
                  <RowActionsCell
                    affordanceType="property"
                    name={property.name}
                    bindings={bindings}
                    onRun={onRun}
                    runRequiresBinding={runRequiresBinding}
                    onOpenBinding={onOpenBinding}
                    bindingHref={bindingHref}
                  />
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableShell>
      ) : (
        <EmptyState>No properties defined.</EmptyState>
      )}
    </ThingSectionCard>
  );
}

export function ThingActionsSection({
  actions,
  bindings,
  onRun,
  runRequiresBinding,
  onOpenBinding,
  bindingHref,
  activeKey,
}: {
  actions: ActionDef[];
} & RowActionsProps) {
  const showActions = hasRowActions({
    bindings,
    onRun,
    runRequiresBinding,
    onOpenBinding,
    bindingHref,
  });
  return (
    <ThingSectionCard
      title="Actions"
      description={
        <>
          {actions.length} action{actions.length === 1 ? '' : 's'} defined in
          this Thing Description.
        </>
      }
    >
      {actions.length > 0 ? (
        <TableShell>
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>Name</TableHead>
                <TableHead>Input</TableHead>
                <TableHead>Output</TableHead>
                <TableHead>Description</TableHead>
                <RowActionsHeadCell show={showActions} />
              </TableRow>
            </TableHeader>
            <TableBody>
              {actions.map((action) => (
                <TableRow
                  key={action.name}
                  className={cn(
                    isActiveRow(activeKey, 'action', action.name) &&
                      'bg-primary/5',
                  )}
                >
                  <NameCell value={action.name} />
                  <TableCell>
                    <SchemaBadge value={action.inputSchema} />
                  </TableCell>
                  <TableCell>
                    <SchemaBadge value={action.outputSchema} />
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {action.description ?? '-'}
                  </TableCell>
                  <RowActionsCell
                    affordanceType="action"
                    name={action.name}
                    bindings={bindings}
                    onRun={onRun}
                    runRequiresBinding={runRequiresBinding}
                    onOpenBinding={onOpenBinding}
                    bindingHref={bindingHref}
                  />
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableShell>
      ) : (
        <EmptyState>No actions defined.</EmptyState>
      )}
    </ThingSectionCard>
  );
}

export function ThingEventsSection({
  events,
  bindings,
  onRun,
  runRequiresBinding,
  onOpenBinding,
  bindingHref,
  activeKey,
}: {
  events: EventDef[];
} & RowActionsProps) {
  const showActions = hasRowActions({
    bindings,
    onRun,
    runRequiresBinding,
    onOpenBinding,
    bindingHref,
  });
  return (
    <ThingSectionCard
      title="Events"
      description={
        <>
          {events.length} event{events.length === 1 ? '' : 's'} defined in this
          Thing Description.
        </>
      }
    >
      {events.length > 0 ? (
        <TableShell>
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>Name</TableHead>
                <TableHead>Data</TableHead>
                <TableHead>Description</TableHead>
                <RowActionsHeadCell show={showActions} />
              </TableRow>
            </TableHeader>
            <TableBody>
              {events.map((event) => (
                <TableRow
                  key={event.name}
                  className={cn(
                    isActiveRow(activeKey, 'event', event.name) &&
                      'bg-primary/5',
                  )}
                >
                  <NameCell value={event.name} />
                  <TableCell>
                    <SchemaBadge value={event.dataSchema} />
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {event.description ?? '-'}
                  </TableCell>
                  <RowActionsCell
                    affordanceType="event"
                    name={event.name}
                    bindings={bindings}
                    onRun={onRun}
                    runRequiresBinding={runRequiresBinding}
                    onOpenBinding={onOpenBinding}
                    bindingHref={bindingHref}
                  />
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableShell>
      ) : (
        <EmptyState>No events defined.</EmptyState>
      )}
    </ThingSectionCard>
  );
}

export function ThingSecuritySection({
  securityStr,
  securityDefs,
  credentialMap,
  onDeleteCredential,
  onOpenCredential,
}: {
  securityStr: string;
  securityDefs: SecurityDefinition[];
  credentialMap: Map<string, StoredCredential>;
  onDeleteCredential: (securityName: string) => Promise<void> | void;
  onOpenCredential: (definition: SecurityDefinition) => void;
}) {
  return (
    <ThingSectionCard
      title={
        <span className="flex items-center gap-2">
          <Shield className="h-5 w-5" />
          Security Definitions
        </span>
      }
      description={
        <>
          Active security: <code>{securityStr}</code>
        </>
      }
    >
      {securityDefs.length > 0 ? (
        <TableShell>
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>Name</TableHead>
                <TableHead>Scheme</TableHead>
                <TableHead>Credentials</TableHead>
                <TableHead>Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {securityDefs.map((definition) => {
                const stored = credentialMap.get(definition.name);
                const hasCredentials = Boolean(stored);

                return (
                  <TableRow key={definition.name}>
                    <NameCell value={definition.name} />
                    <TableCell>
                      <SchemaBadge value={definition.scheme} />
                    </TableCell>
                    <TableCell>
                      {definition.scheme === 'nosec' ? (
                        <span className="text-muted-foreground">N/A</span>
                      ) : hasCredentials ? (
                        <Badge
                          variant="secondary"
                          className="gap-1 text-green-600"
                        >
                          <Lock className="h-3 w-3" />
                          Set
                        </Badge>
                      ) : (
                        <Badge
                          variant="outline"
                          className="text-muted-foreground"
                        >
                          Not set
                        </Badge>
                      )}
                    </TableCell>
                    <TableCell>
                      {definition.scheme !== 'nosec' ? (
                        <div className="flex gap-2">
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => onOpenCredential(definition)}
                          >
                            {hasCredentials ? 'Update' : 'Set credentials'}
                          </Button>
                          {hasCredentials ? (
                            <Button
                              size="sm"
                              variant="destructive"
                              onClick={() =>
                                void onDeleteCredential(definition.name)
                              }
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                            </Button>
                          ) : null}
                        </div>
                      ) : null}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </TableShell>
      ) : (
        <EmptyState>No security definitions found.</EmptyState>
      )}
    </ThingSectionCard>
  );
}
