import { useMemo, type ReactNode } from 'react';

type MarkdownBlock =
  | { text: string; type: 'paragraph' }
  | { level: 1 | 2 | 3; text: string; type: 'heading' }
  | { items: string[]; type: 'ordered-list' | 'unordered-list' }
  | { code: string; type: 'code' };

function isMarkdownBlockStart(line: string) {
  return (
    /^#{1,3}\s+/.test(line) ||
    /^[-*]\s+/.test(line) ||
    /^\d+\.\s+/.test(line) ||
    /^```/.test(line)
  );
}

function parseMarkdownBlocks(text: string): MarkdownBlock[] {
  const lines = text.replace(/\r\n/g, '\n').split('\n');
  const blocks: MarkdownBlock[] = [];
  let index = 0;

  while (index < lines.length) {
    const line = lines[index] ?? '';
    const trimmed = line.trim();

    if (!trimmed) {
      index += 1;
      continue;
    }

    if (/^```/.test(trimmed)) {
      index += 1;
      const codeLines: string[] = [];
      while (index < lines.length && !/^```/.test(lines[index]?.trim() ?? '')) {
        codeLines.push(lines[index] ?? '');
        index += 1;
      }
      if (index < lines.length) {
        index += 1;
      }
      blocks.push({ code: codeLines.join('\n'), type: 'code' });
      continue;
    }

    const heading = /^(#{1,3})\s+(.+)$/.exec(trimmed);
    if (heading) {
      blocks.push({
        level: heading[1].length as 1 | 2 | 3,
        text: heading[2],
        type: 'heading',
      });
      index += 1;
      continue;
    }

    if (/^[-*]\s+/.test(trimmed)) {
      const items: string[] = [];
      while (index < lines.length) {
        const match = /^[-*]\s+(.+)$/.exec(lines[index]?.trim() ?? '');
        if (!match) {
          break;
        }
        items.push(match[1]);
        index += 1;
      }
      blocks.push({ items, type: 'unordered-list' });
      continue;
    }

    if (/^\d+\.\s+/.test(trimmed)) {
      const items: string[] = [];
      while (index < lines.length) {
        const match = /^\d+\.\s+(.+)$/.exec(lines[index]?.trim() ?? '');
        if (!match) {
          break;
        }
        items.push(match[1]);
        index += 1;
      }
      blocks.push({ items, type: 'ordered-list' });
      continue;
    }

    const paragraphLines: string[] = [];
    while (index < lines.length) {
      const candidate = lines[index]?.trim() ?? '';
      if (
        !candidate ||
        (paragraphLines.length > 0 && isMarkdownBlockStart(candidate))
      ) {
        break;
      }
      paragraphLines.push(candidate);
      index += 1;
    }
    blocks.push({ text: paragraphLines.join(' '), type: 'paragraph' });
  }

  return blocks;
}

function safeHref(href: string) {
  return /^(https?:\/\/|\/|#)/i.test(href) ? href : undefined;
}

function renderInlineMarkdown(text: string, keyPrefix: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  const tokenPattern = /(`[^`]+`|\*\*[^*]+\*\*|\*[^*]+\*|\[[^\]]+\]\([^)]+\))/g;
  let cursor = 0;
  let match: RegExpExecArray | null;

  while ((match = tokenPattern.exec(text)) !== null) {
    if (match.index > cursor) {
      nodes.push(text.slice(cursor, match.index));
    }

    const token = match[0];
    const key = `${keyPrefix}-${match.index}`;
    if (token.startsWith('`')) {
      nodes.push(
        <code className="rounded bg-muted px-1 py-0.5 text-sm" key={key}>
          {token.slice(1, -1)}
        </code>,
      );
    } else if (token.startsWith('**')) {
      nodes.push(<strong key={key}>{token.slice(2, -2)}</strong>);
    } else if (token.startsWith('*')) {
      nodes.push(<em key={key}>{token.slice(1, -1)}</em>);
    } else {
      const link = /^\[([^\]]+)\]\(([^)]+)\)$/.exec(token);
      const href = link ? safeHref(link[2]) : undefined;
      nodes.push(
        href ? (
          <a
            className="text-primary underline underline-offset-4"
            href={href}
            key={key}
            rel="noreferrer"
            target={href.startsWith('http') ? '_blank' : undefined}
          >
            {link?.[1]}
          </a>
        ) : (
          token
        ),
      );
    }

    cursor = match.index + token.length;
  }

  if (cursor < text.length) {
    nodes.push(text.slice(cursor));
  }

  return nodes;
}

export function LiveResponseMarkdown({ text }: { text: string }) {
  const blocks = useMemo(() => parseMarkdownBlocks(text), [text]);

  return (
    <div className="mx-auto max-w-2xl space-y-4 text-left text-base leading-7 text-foreground md:text-lg">
      {blocks.map((block, index) => {
        const key = `${block.type}-${index}`;
        if (block.type === 'heading') {
          const Heading = `h${block.level}` as 'h1' | 'h2' | 'h3';
          return (
            <Heading
              className="text-xl font-semibold tracking-tight text-foreground md:text-2xl"
              key={key}
            >
              {renderInlineMarkdown(block.text, key)}
            </Heading>
          );
        }
        if (block.type === 'code') {
          return (
            <pre
              className="overflow-auto rounded-lg border border-border bg-muted p-3 text-sm leading-6"
              key={key}
            >
              <code>{block.code}</code>
            </pre>
          );
        }
        if (block.type === 'unordered-list') {
          return (
            <ul className="list-disc space-y-1 pl-6" key={key}>
              {block.items.map((item, itemIndex) => (
                <li key={`${key}-${itemIndex}`}>
                  {renderInlineMarkdown(item, `${key}-${itemIndex}`)}
                </li>
              ))}
            </ul>
          );
        }
        if (block.type === 'ordered-list') {
          return (
            <ol className="list-decimal space-y-1 pl-6" key={key}>
              {block.items.map((item, itemIndex) => (
                <li key={`${key}-${itemIndex}`}>
                  {renderInlineMarkdown(item, `${key}-${itemIndex}`)}
                </li>
              ))}
            </ol>
          );
        }
        if (block.type === 'paragraph') {
          return <p key={key}>{renderInlineMarkdown(block.text, key)}</p>;
        }
        return null;
      })}
    </div>
  );
}

export function AssistantThinkingDots() {
  return (
    <div
      aria-label="Waiting for assistant response"
      className="flex justify-start"
      role="status"
    >
      <div className="flex h-9 items-center gap-1.5 rounded-full border border-border bg-muted/50 px-3">
        <span className="size-1.5 animate-bounce rounded-full bg-muted-foreground" />
        <span
          className="size-1.5 animate-bounce rounded-full bg-muted-foreground"
          style={{ animationDelay: '120ms' }}
        />
        <span
          className="size-1.5 animate-bounce rounded-full bg-muted-foreground"
          style={{ animationDelay: '240ms' }}
        />
      </div>
    </div>
  );
}
