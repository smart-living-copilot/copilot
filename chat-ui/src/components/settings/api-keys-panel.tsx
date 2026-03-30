'use client';

import { useCallback, useEffect, useState } from 'react';
import { Copy, KeyRound, Plus, Trash2 } from 'lucide-react';
import { toast } from 'sonner';

import { httpClient, httpJson } from '@/lib/http-client';
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
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';

const ALL_SCOPES = [
  'things:read',
  'things:write',
  'things:delete',
  'wot:read',
  'wot:write',
  'content:read',
  'content:write',
  'search:read',
  'credentials:read',
  'credentials:write',
  'keys:manage',
] as const;

interface ApiKey {
  id: string;
  key_prefix: string;
  name: string;
  scopes: string[];
  user_id: string;
  created_at: string;
  updated_at: string;
  expires_at: string | null;
  last_used_at: string | null;
  is_active: boolean;
}

function formatDate(iso: string | null): string {
  if (!iso) return 'Never';
  return new Date(iso).toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function ApiKeysPanel() {
  const [keys, setKeys] = useState<ApiKey[]>([]);
  const [loading, setLoading] = useState(true);
  const [createOpen, setCreateOpen] = useState(false);
  const [revokeTarget, setRevokeTarget] = useState<ApiKey | null>(null);
  const [rawKey, setRawKey] = useState<string | null>(null);

  // Create form state
  const [newName, setNewName] = useState('');
  const [newScopes, setNewScopes] = useState<Set<string>>(new Set());
  const [newExpiry, setNewExpiry] = useState('');
  const [creating, setCreating] = useState(false);

  const loadKeys = useCallback(async () => {
    try {
      const data = await httpJson<{ items: ApiKey[] }>('/keys');
      setKeys(data.items);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to load keys');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadKeys();
  }, [loadKeys]);

  const handleCreate = async () => {
    if (!newName.trim() || newScopes.size === 0) return;
    setCreating(true);
    try {
      const body: Record<string, unknown> = {
        name: newName.trim(),
        scopes: Array.from(newScopes),
      };
      if (newExpiry) body.expires_at = new Date(newExpiry).toISOString();

      const result = await httpJson<{ key: ApiKey; raw_key: string }>('/keys', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      setCreateOpen(false);
      setNewName('');
      setNewScopes(new Set());
      setNewExpiry('');
      setRawKey(result.raw_key);
      await loadKeys();
      toast.success('API key created');
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to create key');
    } finally {
      setCreating(false);
    }
  };

  const handleRevoke = async () => {
    if (!revokeTarget) return;
    try {
      await httpClient(`/keys/${revokeTarget.id}`, { method: 'DELETE' });
      setRevokeTarget(null);
      await loadKeys();
      toast.success('API key revoked');
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to revoke key');
    }
  };

  const toggleScope = (scope: string) => {
    setNewScopes((prev) => {
      const next = new Set(prev);
      if (next.has(scope)) next.delete(scope);
      else next.add(scope);
      return next;
    });
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight">API Keys</h2>
          <p className="text-sm text-muted-foreground">
            Create and manage API keys for programmatic access.
          </p>
        </div>
        <Button onClick={() => setCreateOpen(true)}>
          <Plus className="mr-2 size-4" />
          Create Key
        </Button>
      </div>

      {loading ? (
        <p className="text-sm text-muted-foreground">Loading...</p>
      ) : keys.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12">
            <KeyRound className="mb-4 size-12 text-muted-foreground" />
            <p className="text-sm text-muted-foreground">
              No API keys yet. Create one to get started.
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {keys.map((k) => (
            <Card key={k.id}>
              <CardHeader className="pb-3">
                <div className="flex items-start justify-between">
                  <div>
                    <CardTitle className="text-base">{k.name}</CardTitle>
                    <CardDescription className="font-mono text-xs">
                      {k.key_prefix}...
                    </CardDescription>
                  </div>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    onClick={() => setRevokeTarget(k)}
                  >
                    <Trash2 className="size-4 text-destructive" />
                  </Button>
                </div>
              </CardHeader>
              <CardContent>
                <div className="flex flex-wrap gap-1.5">
                  {k.scopes.map((s) => (
                    <Badge key={s} variant="secondary">
                      {s}
                    </Badge>
                  ))}
                </div>
                <div className="mt-3 flex gap-4 text-xs text-muted-foreground">
                  <span>Created {formatDate(k.created_at)}</span>
                  <span>Last used {formatDate(k.last_used_at)}</span>
                  {k.expires_at && (
                    <span>Expires {formatDate(k.expires_at)}</span>
                  )}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Create dialog */}
      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Create API Key</DialogTitle>
            <DialogDescription>
              The key will only be shown once after creation.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div>
              <label className="text-sm font-medium" htmlFor="key-name">
                Name
              </label>
              <Input
                id="key-name"
                placeholder="My integration"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
              />
            </div>
            <div>
              <label className="mb-2 block text-sm font-medium">Scopes</label>
              <div className="grid grid-cols-2 gap-2">
                {ALL_SCOPES.map((scope) => (
                  <label
                    key={scope}
                    className="flex cursor-pointer items-center gap-2 text-sm"
                  >
                    <input
                      type="checkbox"
                      checked={newScopes.has(scope)}
                      onChange={() => toggleScope(scope)}
                      className="size-4 rounded accent-primary"
                    />
                    {scope}
                  </label>
                ))}
              </div>
            </div>
            <div>
              <label className="text-sm font-medium" htmlFor="key-expiry">
                Expiry (optional)
              </label>
              <Input
                id="key-expiry"
                type="date"
                value={newExpiry}
                onChange={(e) => setNewExpiry(e.target.value)}
              />
            </div>
          </div>
          <DialogFooter>
            <DialogClose asChild>
              <Button variant="outline">Cancel</Button>
            </DialogClose>
            <Button
              onClick={() => void handleCreate()}
              disabled={creating || !newName.trim() || newScopes.size === 0}
            >
              {creating ? 'Creating...' : 'Create'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Raw key display dialog */}
      <Dialog
        open={rawKey !== null}
        onOpenChange={(open) => {
          if (!open) setRawKey(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Your API Key</DialogTitle>
            <DialogDescription>
              Copy this key now. You won&apos;t be able to see it again.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <div className="flex items-center gap-2 rounded-md bg-muted p-3">
              <code className="flex-1 break-all text-sm">{rawKey}</code>
              <Button
                variant="ghost"
                size="icon-sm"
                onClick={() => {
                  if (rawKey) {
                    void navigator.clipboard.writeText(rawKey);
                    toast.success('Copied to clipboard');
                  }
                }}
              >
                <Copy className="size-4" />
              </Button>
            </div>
            <p className="text-sm font-medium text-amber-600 dark:text-amber-400">
              Store this key securely. It will not be displayed again.
            </p>
          </div>
          <DialogFooter>
            <Button onClick={() => setRawKey(null)}>Done</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Revoke confirmation dialog */}
      <Dialog
        open={revokeTarget !== null}
        onOpenChange={(open) => {
          if (!open) setRevokeTarget(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Revoke API Key</DialogTitle>
            <DialogDescription>
              Are you sure you want to revoke &quot;{revokeTarget?.name}&quot;?
              This action cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRevokeTarget(null)}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={() => void handleRevoke()}>
              Revoke
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
