'use client';

import { type ReactNode } from 'react';
import { Check, Lock, Shield, Trash2, X } from 'lucide-react';

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

import {
  type ActionDef,
  type EventDef,
  type PropertyDef,
  type SecurityDefinition,
  type StoredCredential,
} from './thing-detail-model';

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
    <Card className="border border-border/70 shadow-sm shadow-black/5">
      <CardHeader>
        <CardTitle className="text-2xl">{title}</CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}

function TableShell({ children }: { children: ReactNode }) {
  return <div className="rounded-xl border border-border/70">{children}</div>;
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
}: {
  properties: PropertyDef[];
}) {
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
              </TableRow>
            </TableHeader>
            <TableBody>
              {properties.map((property) => (
                <TableRow key={property.name}>
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

export function ThingActionsSection({ actions }: { actions: ActionDef[] }) {
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
              </TableRow>
            </TableHeader>
            <TableBody>
              {actions.map((action) => (
                <TableRow key={action.name}>
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

export function ThingEventsSection({ events }: { events: EventDef[] }) {
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
              </TableRow>
            </TableHeader>
            <TableBody>
              {events.map((event) => (
                <TableRow key={event.name}>
                  <NameCell value={event.name} />
                  <TableCell>
                    <SchemaBadge value={event.dataSchema} />
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {event.description ?? '-'}
                  </TableCell>
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
