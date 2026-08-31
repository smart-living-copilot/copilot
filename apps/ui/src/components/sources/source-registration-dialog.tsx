'use client';

import { Loader2 } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { toast } from 'sonner';

import { CredentialDialog } from '@/components/things/thing-detail-credential-dialog';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import {
  type DiscoverySource,
  type ProviderSchema,
  type SourceCredentialChallenge,
  type SourceDraft,
  fetchProviderSchemas,
  registerDetectedSource,
  saveSource,
} from '@/lib/sources-api';

export function SourceRegistrationDialog({
  open,
  onOpenChange,
  onRegistered,
  source,
  initialDraft,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onRegistered: (source: DiscoverySource) => void;
  source?: DiscoverySource | null;
  initialDraft?: SourceDraft | null;
}) {
  const editing = Boolean(source);
  const [providers, setProviders] = useState<ProviderSchema[]>([]);
  const [mode, setMode] = useState<'detect' | 'manual'>('detect');
  const [url, setUrl] = useState('');
  const [providerName, setProviderName] = useState('');
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [tags, setTags] = useState('');
  const [networkAccess, setNetworkAccess] = useState<'public' | 'private'>(
    'public',
  );
  const [privateConfirmed, setPrivateConfirmed] = useState(false);
  const [securityName, setSecurityName] = useState('source_sc');
  const [securityScheme, setSecurityScheme] = useState('nosec');
  const [config, setConfig] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [credentialChallenge, setCredentialChallenge] =
    useState<SourceCredentialChallenge | null>(null);
  const [pendingSource, setPendingSource] = useState<DiscoverySource | null>(
    null,
  );

  useEffect(() => {
    if (!open) return;
    void fetchProviderSchemas()
      .then(setProviders)
      .catch((error) =>
        toast.error(
          error instanceof Error ? error.message : 'Could not load providers',
        ),
      );
  }, [open]);

  useEffect(() => {
    if (!open) return;
    setPrivateConfirmed(false);
    if (source) {
      setMode('manual');
      setProviderName(source.provider);
      setTitle(source.title);
      setDescription(source.description);
      setTags(source.tags.join(', '));
      setNetworkAccess(source.network_access);
      setSecurityName(source.security_name);
      setSecurityScheme(source.security_scheme);
      setConfig(
        Object.fromEntries(
          Object.entries(source.config).map(([key, value]) => [
            key,
            String(value),
          ]),
        ),
      );
      return;
    }
    const draft = initialDraft || {};
    setMode(draft.url && !draft.provider ? 'detect' : 'manual');
    setUrl(draft.url || '');
    setProviderName(draft.provider || '');
    setTitle(draft.title || '');
    setDescription(draft.description || '');
    setTags((draft.tags || []).join(', '));
    setNetworkAccess('public');
    setSecurityName('source_sc');
    setSecurityScheme(draft.security_scheme || 'nosec');
    setConfig(
      Object.fromEntries(
        Object.entries({
          ...(draft.provider && draft.url ? { url: draft.url } : {}),
          ...(draft.config || {}),
        }).map(([key, value]) => [key, String(value ?? '')]),
      ),
    );
  }, [initialDraft, open, source]);

  const provider = useMemo(
    () =>
      providers.find((item) => item.provider === providerName) ?? providers[0],
    [providerName, providers],
  );

  useEffect(() => {
    if (!provider || editing) return;
    if (!providerName) setProviderName(provider.provider);
    if (!initialDraft?.security_scheme) {
      setSecurityScheme(provider.default_security_scheme);
    }
    setConfig((current) => ({
      ...Object.fromEntries(
        Object.entries(provider.config_schema.properties || {}).map(
          ([field, schema]) => [field, String(schema.default ?? '')],
        ),
      ),
      ...current,
    }));
  }, [editing, initialDraft?.security_scheme, provider, providerName]);

  async function handleSubmit() {
    setSaving(true);
    try {
      const result =
        !editing && mode === 'detect'
          ? await registerDetectedSource(url, networkAccess)
          : await saveSource(
              {
                provider: provider?.provider || '',
                title,
                description,
                tags: tags
                  .split(',')
                  .map((item) => item.trim())
                  .filter(Boolean),
                network_access: networkAccess,
                security: { name: securityName, scheme: securityScheme },
                config: Object.fromEntries(
                  Object.entries(config).map(([field, value]) => [
                    field,
                    provider?.config_schema.properties?.[field]?.type ===
                    'number'
                      ? Number(value)
                      : value,
                  ]),
                ),
              },
              source?.source_id,
            );
      if (result.unsupported_source || !result.source) {
        throw new Error(
          `Unsupported source. ${(result.probe_evidence || []).join(' ')}`.trim(),
        );
      }
      toast.success(editing ? 'Source updated' : 'Source registered');
      onOpenChange(false);
      if (result.credential_challenge) {
        setPendingSource(result.source);
        setCredentialChallenge(result.credential_challenge);
      } else {
        onRegistered(result.source);
      }
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : 'Could not save source',
      );
    } finally {
      setSaving(false);
    }
  }

  const configFields = Object.entries(provider?.config_schema.properties || {});
  const requiresPrivateConfirmation =
    networkAccess === 'private' && !privateConfirmed;

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>
              {editing ? 'Edit discovery source' : 'Register discovery source'}
            </DialogTitle>
            <DialogDescription>
              Source configuration stays in the discovery control plane. Secret
              values are stored separately and never sent through chat.
            </DialogDescription>
          </DialogHeader>

          {!editing ? (
            <div className="flex gap-2">
              <Button
                type="button"
                variant={mode === 'detect' ? 'default' : 'outline'}
                onClick={() => setMode('detect')}
              >
                Detect URL
              </Button>
              <Button
                type="button"
                variant={mode === 'manual' ? 'default' : 'outline'}
                onClick={() => setMode('manual')}
              >
                Configure provider
              </Button>
            </div>
          ) : null}

          {!editing && mode === 'detect' ? (
            <div className="space-y-4">
              <label className="block space-y-1.5 text-sm font-medium">
                Source URL
                <Input
                  type="url"
                  value={url}
                  onChange={(event) => setUrl(event.target.value)}
                  placeholder="https://data.public.lu/en/"
                />
              </label>
              <NetworkFields
                networkAccess={networkAccess}
                privateConfirmed={privateConfirmed}
                setNetworkAccess={setNetworkAccess}
                setPrivateConfirmed={setPrivateConfirmed}
              />
            </div>
          ) : (
            <div className="space-y-4">
              <label className="block space-y-1.5 text-sm font-medium">
                Provider
                <select
                  className="flex h-9 w-full rounded-lg border border-input bg-transparent px-2.5 text-sm"
                  value={provider?.provider || ''}
                  disabled={editing}
                  onChange={(event) => {
                    setProviderName(event.target.value);
                    setConfig({});
                  }}
                >
                  {providers.map((item) => (
                    <option key={item.provider} value={item.provider}>
                      {item.title}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block space-y-1.5 text-sm font-medium">
                Title
                <Input
                  value={title}
                  onChange={(event) => setTitle(event.target.value)}
                />
              </label>
              <label className="block space-y-1.5 text-sm font-medium">
                Description
                <Textarea
                  value={description}
                  onChange={(event) => setDescription(event.target.value)}
                />
              </label>
              <label className="block space-y-1.5 text-sm font-medium">
                Tags (comma separated)
                <Input
                  value={tags}
                  onChange={(event) => setTags(event.target.value)}
                />
              </label>
              <NetworkFields
                networkAccess={networkAccess}
                privateConfirmed={privateConfirmed}
                setNetworkAccess={setNetworkAccess}
                setPrivateConfirmed={setPrivateConfirmed}
              />
              <div className="grid gap-4 sm:grid-cols-2">
                <label className="block space-y-1.5 text-sm font-medium">
                  Security name
                  <Input
                    value={securityName}
                    onChange={(event) => setSecurityName(event.target.value)}
                  />
                </label>
                <label className="block space-y-1.5 text-sm font-medium">
                  Credential scheme
                  <select
                    className="flex h-9 w-full rounded-lg border border-input bg-transparent px-2.5 text-sm"
                    value={securityScheme}
                    onChange={(event) => setSecurityScheme(event.target.value)}
                  >
                    {(provider?.security_schemes || ['nosec']).map((scheme) => (
                      <option key={scheme} value={scheme}>
                        {scheme}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              {configFields.map(([field, schema]) => (
                <label
                  key={field}
                  className="block space-y-1.5 text-sm font-medium"
                >
                  {field.replaceAll('_', ' ')}
                  <Input
                    type={
                      schema.format === 'uri'
                        ? 'url'
                        : schema.type === 'number'
                          ? 'number'
                          : 'text'
                    }
                    required={provider?.config_schema.required?.includes(field)}
                    step={schema.type === 'number' ? 'any' : undefined}
                    value={config[field] || ''}
                    onChange={(event) =>
                      setConfig((current) => ({
                        ...current,
                        [field]: event.target.value,
                      }))
                    }
                  />
                </label>
              ))}
            </div>
          )}

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
            >
              Cancel
            </Button>
            <Button
              type="button"
              disabled={
                saving ||
                requiresPrivateConfirmation ||
                (!editing && mode === 'detect' && !url.trim())
              }
              onClick={() => void handleSubmit()}
            >
              {saving ? <Loader2 className="animate-spin" /> : null}
              {editing ? 'Save source' : 'Confirm registration'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {credentialChallenge ? (
        <CredentialDialog
          open
          onOpenChange={(nextOpen) => {
            if (!nextOpen) {
              setCredentialChallenge(null);
              if (pendingSource) onRegistered(pendingSource);
              setPendingSource(null);
            }
          }}
          sourceId={credentialChallenge.source_id}
          secDef={{
            name: credentialChallenge.security_name,
            scheme: credentialChallenge.scheme,
          }}
          onSaved={() => undefined}
        />
      ) : null}
    </>
  );
}

function NetworkFields({
  networkAccess,
  privateConfirmed,
  setNetworkAccess,
  setPrivateConfirmed,
}: {
  networkAccess: 'public' | 'private';
  privateConfirmed: boolean;
  setNetworkAccess: (value: 'public' | 'private') => void;
  setPrivateConfirmed: (value: boolean) => void;
}) {
  return (
    <div className="space-y-2">
      <label className="block space-y-1.5 text-sm font-medium">
        Network access
        <select
          className="flex h-9 w-full rounded-lg border border-input bg-transparent px-2.5 text-sm"
          value={networkAccess}
          onChange={(event) => {
            setNetworkAccess(event.target.value as 'public' | 'private');
            setPrivateConfirmed(false);
          }}
        >
          <option value="public">Public network only</option>
          <option value="private">Private network allowed</option>
        </select>
      </label>
      {networkAccess === 'private' ? (
        <label className="flex items-start gap-2 rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-950">
          <input
            className="mt-1"
            type="checkbox"
            checked={privateConfirmed}
            onChange={(event) => setPrivateConfirmed(event.target.checked)}
          />
          I confirm that this source may be probed and contacted on the private
          network.
        </label>
      ) : null}
    </div>
  );
}
