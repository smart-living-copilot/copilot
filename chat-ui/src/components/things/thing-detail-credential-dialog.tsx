'use client';

import { useEffect, useState } from 'react';
import { Check, Eye, EyeOff, Loader2 } from 'lucide-react';
import { toast } from 'sonner';

import { httpClient } from '@/lib/http-client';
import { Button } from '@/components/ui/button';
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

import {
  CREDENTIAL_FIELDS,
  CREDENTIAL_KEYS,
  type SecurityDefinition,
} from './thing-detail-model';

export function CredentialDialog({
  open,
  onOpenChange,
  thingId,
  secDef,
  onSaved,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  thingId: string;
  secDef: SecurityDefinition;
  onSaved: () => void;
}) {
  const fields = CREDENTIAL_FIELDS[secDef.scheme] ?? [];
  const keys = CREDENTIAL_KEYS[secDef.scheme] ?? [];
  const [values, setValues] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [showPasswords, setShowPasswords] = useState<Record<string, boolean>>(
    {},
  );

  useEffect(() => {
    if (open) {
      setValues({});
      setShowPasswords({});
    }
  }, [open]);

  async function handleSave() {
    const credentials: Record<string, string> = {};

    for (const key of keys) {
      credentials[key] = values[key] ?? '';
    }

    setSaving(true);

    try {
      await httpClient(
        `/credentials/${encodeURIComponent(thingId)}/${encodeURIComponent(secDef.name)}`,
        {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            scheme: secDef.scheme,
            credentials,
          }),
        },
      );
      toast.success(`Credentials saved for ${secDef.name}`);
      onSaved();
      onOpenChange(false);
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : 'Failed to save credentials',
      );
    } finally {
      setSaving(false);
    }
  }

  if (secDef.scheme === 'nosec') {
    return (
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{secDef.name}</DialogTitle>
            <DialogDescription>
              No security — no credentials needed.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <DialogClose asChild>
              <Button variant="outline">Close</Button>
            </DialogClose>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    );
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Credentials for &quot;{secDef.name}&quot;</DialogTitle>
          <DialogDescription>
            Scheme: <code>{secDef.scheme}</code>
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-2">
          {fields.map((field, index) => {
            const key = keys[index];
            const isPassword = field.type === 'password';
            const show = showPasswords[key] ?? false;

            return (
              <div key={key} className="space-y-1.5">
                <label className="text-sm font-medium">{field.label}</label>
                <div className="relative">
                  <Input
                    type={isPassword && !show ? 'password' : 'text'}
                    value={values[key] ?? ''}
                    onChange={(event) =>
                      setValues((current) => ({
                        ...current,
                        [key]: event.target.value,
                      }))
                    }
                    className={isPassword ? 'pr-10' : ''}
                  />
                  {isPassword ? (
                    <button
                      type="button"
                      onClick={() =>
                        setShowPasswords((current) => ({
                          ...current,
                          [key]: !current[key],
                        }))
                      }
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                    >
                      {show ? (
                        <EyeOff className="h-4 w-4" />
                      ) : (
                        <Eye className="h-4 w-4" />
                      )}
                    </button>
                  ) : null}
                </div>
              </div>
            );
          })}
        </div>
        <DialogFooter>
          <DialogClose asChild>
            <Button variant="outline">Cancel</Button>
          </DialogClose>
          <Button onClick={() => void handleSave()} disabled={saving}>
            {saving ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Check className="h-4 w-4" />
            )}
            Save
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
