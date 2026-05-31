'use client';

import { useCallback, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { CheckCircle2, FileJson, Loader2, Upload, XCircle } from 'lucide-react';
import { toast } from 'sonner';

import { createThing } from '@/lib/things-api';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';

interface FileEntry {
  name: string;
  status: 'pending' | 'uploading' | 'success' | 'error';
  error?: string;
  thingId?: string;
}

function parseJsonFile(file: File): Promise<Record<string, unknown>> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      try {
        const parsed = JSON.parse(reader.result as string);
        if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
          reject(new Error('File must contain a JSON object'));
          return;
        }
        resolve(parsed as Record<string, unknown>);
      } catch {
        reject(new Error('Invalid JSON'));
      }
    };
    reader.onerror = () => reject(new Error('Failed to read file'));
    reader.readAsText(file);
  });
}

export function ThingFileUpload() {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<FileEntry[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [isDragOver, setIsDragOver] = useState(false);

  const addFiles = useCallback((fileList: FileList) => {
    const jsonFiles = Array.from(fileList).filter(
      (f) => f.name.endsWith('.json') || f.name.endsWith('.jsonld'),
    );
    if (jsonFiles.length === 0) {
      toast.error('Please select JSON files');
      return;
    }

    setFiles((prev) => [
      ...prev,
      ...jsonFiles
        .filter((f) => !prev.some((existing) => existing.name === f.name))
        .map((f) => ({ name: f.name, status: 'pending' as const })),
    ]);

    // Store files for later upload
    if (inputRef.current) {
      const dt = new DataTransfer();
      // Keep existing files from input
      if (inputRef.current.files) {
        for (const f of Array.from(inputRef.current.files)) {
          if (!jsonFiles.some((jf) => jf.name === f.name)) dt.items.add(f);
        }
      }
      for (const f of jsonFiles) dt.items.add(f);
      inputRef.current.files = dt.files;
    }
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragOver(false);
      if (e.dataTransfer.files.length > 0) {
        addFiles(e.dataTransfer.files);
      }
    },
    [addFiles],
  );

  const removeFile = useCallback((name: string) => {
    setFiles((prev) => prev.filter((f) => f.name !== name));
  }, []);

  const handleUploadAll = useCallback(async () => {
    const inputFiles = inputRef.current?.files;
    if (!inputFiles || files.length === 0) return;

    setIsUploading(true);
    const fileMap = new Map<string, File>();
    for (const f of Array.from(inputFiles)) {
      fileMap.set(f.name, f);
    }

    let successCount = 0;
    for (const entry of files) {
      if (entry.status === 'success') {
        successCount++;
        continue;
      }

      const file = fileMap.get(entry.name);
      if (!file) {
        setFiles((prev) =>
          prev.map((f) =>
            f.name === entry.name
              ? { ...f, status: 'error', error: 'File not found' }
              : f,
          ),
        );
        continue;
      }

      setFiles((prev) =>
        prev.map((f) =>
          f.name === entry.name ? { ...f, status: 'uploading' } : f,
        ),
      );

      try {
        const document = await parseJsonFile(file);
        const result = await createThing(document);
        setFiles((prev) =>
          prev.map((f) =>
            f.name === entry.name
              ? { ...f, status: 'success', thingId: result.id }
              : f,
          ),
        );
        successCount++;
      } catch (error) {
        setFiles((prev) =>
          prev.map((f) =>
            f.name === entry.name
              ? {
                  ...f,
                  status: 'error',
                  error: error instanceof Error ? error.message : 'Failed',
                }
              : f,
          ),
        );
      }
    }

    setIsUploading(false);

    if (successCount === files.length) {
      toast.success(
        `Created ${successCount} thing${successCount === 1 ? '' : 's'}`,
      );
      router.push('/things');
    } else if (successCount > 0) {
      toast.warning(`Created ${successCount} of ${files.length} things`);
    }
  }, [files, router]);

  const pendingCount = files.filter(
    (f) => f.status === 'pending' || f.status === 'error',
  ).length;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Upload JSON files</h2>
        {files.length > 0 && (
          <Button
            size="sm"
            onClick={() => void handleUploadAll()}
            disabled={isUploading || pendingCount === 0}
          >
            {isUploading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Upload className="h-4 w-4" />
            )}
            Create {pendingCount} thing{pendingCount === 1 ? '' : 's'}
          </Button>
        )}
      </div>

      <Card>
        <CardContent className="p-0">
          <div
            className={`flex min-h-40 cursor-pointer flex-col items-center justify-center gap-3 rounded-lg border-2 border-dashed p-8 transition-colors ${
              isDragOver
                ? 'border-primary bg-primary/5'
                : 'border-muted-foreground/25 hover:border-primary/50'
            }`}
            onClick={() => inputRef.current?.click()}
            onDragOver={(e) => {
              e.preventDefault();
              setIsDragOver(true);
            }}
            onDragLeave={() => setIsDragOver(false)}
            onDrop={handleDrop}
          >
            <FileJson className="h-10 w-10 text-muted-foreground/50" />
            <div className="text-center">
              <p className="text-sm font-medium">
                Drop JSON files here or click to browse
              </p>
              <p className="text-xs text-muted-foreground">
                Each file should contain a WoT Thing Description
              </p>
            </div>
          </div>

          <input
            ref={inputRef}
            type="file"
            accept=".json,.jsonld"
            multiple
            className="hidden"
            onChange={(e) => {
              if (e.target.files) addFiles(e.target.files);
            }}
          />

          {files.length > 0 && (
            <ul className="divide-y">
              {files.map((entry) => (
                <li
                  key={entry.name}
                  className="flex items-center gap-3 px-4 py-3"
                >
                  <FileJson className="h-4 w-4 shrink-0 text-muted-foreground" />
                  <span className="min-w-0 flex-1 truncate text-sm">
                    {entry.name}
                  </span>

                  {entry.status === 'uploading' && (
                    <Loader2 className="h-4 w-4 animate-spin text-primary" />
                  )}
                  {entry.status === 'success' && (
                    <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                  )}
                  {entry.status === 'error' && (
                    <span className="flex items-center gap-1 text-xs text-destructive">
                      <XCircle className="h-4 w-4" />
                      {entry.error}
                    </span>
                  )}
                  {(entry.status === 'pending' || entry.status === 'error') &&
                    !isUploading && (
                      <button
                        className="text-xs text-muted-foreground hover:text-foreground"
                        onClick={() => removeFile(entry.name)}
                        type="button"
                      >
                        Remove
                      </button>
                    )}
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
