"use client";

import type { ReactNode } from "react";

function safeLinkTarget(value: string): string | undefined {
  const target = value.trim();
  if (target.startsWith("#") || target.startsWith("/")) return target;
  try {
    const parsed = new URL(target);
    return ["http:", "https:", "mailto:"].includes(parsed.protocol) ? target : undefined;
  } catch {
    return undefined;
  }
}

function textWithBreaks(value: string, keyPrefix: string): ReactNode[] {
  return value.split("\n").flatMap((line, index, lines) => [
    line,
    ...(index < lines.length - 1 ? [<br key={`${keyPrefix}-br-${index}`} />] : []),
  ]);
}

function inlineMarkdown(value: string, keyPrefix: string, depth = 0): ReactNode[] {
  if (depth > 4) return textWithBreaks(value, keyPrefix);
  const pattern = /(`[^`\n]+`|\[([^\]]+)\]\(([^)\s]+)(?:\s+"[^"]*")?\)|\*\*([^*]+)\*\*|__([^_]+)__|~~([^~]+)~~|\*([^*\n]+)\*|_([^_\n]+)_)/g;
  const output: ReactNode[] = [];
  let cursor = 0;
  let match: RegExpExecArray | null;
  let tokenIndex = 0;
  while ((match = pattern.exec(value)) !== null) {
    if (match.index > cursor) output.push(...textWithBreaks(value.slice(cursor, match.index), `${keyPrefix}-text-${tokenIndex}`));
    const tokenKey = `${keyPrefix}-token-${tokenIndex}`;
    if (match[0].startsWith("`")) {
      output.push(<code key={tokenKey}>{match[0].slice(1, -1)}</code>);
    } else if (match[2] !== undefined && match[3] !== undefined) {
      const href = safeLinkTarget(match[3]);
      output.push(href
        ? <a href={href} target="_blank" rel="noreferrer noopener" key={tokenKey}>{inlineMarkdown(match[2], `${tokenKey}-link`, depth + 1)}</a>
        : <span key={tokenKey}>{match[2]} ({match[3]})</span>);
    } else if (match[4] !== undefined || match[5] !== undefined) {
      const content = match[4] ?? match[5];
      output.push(<strong key={tokenKey}>{inlineMarkdown(content, `${tokenKey}-strong`, depth + 1)}</strong>);
    } else if (match[6] !== undefined) {
      output.push(<del key={tokenKey}>{inlineMarkdown(match[6], `${tokenKey}-del`, depth + 1)}</del>);
    } else {
      const content = match[7] ?? match[8] ?? "";
      output.push(<em key={tokenKey}>{inlineMarkdown(content, `${tokenKey}-em`, depth + 1)}</em>);
    }
    cursor = pattern.lastIndex;
    tokenIndex += 1;
  }
  if (cursor < value.length) output.push(...textWithBreaks(value.slice(cursor), `${keyPrefix}-tail`));
  return output;
}

function tableCells(line: string): string[] {
  return line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((cell) => cell.trim());
}

function isTableDivider(line: string): boolean {
  const cells = tableCells(line);
  return cells.length > 0 && cells.every((cell) => /^:?-{3,}:?$/.test(cell));
}

function isBlockStart(lines: string[], index: number): boolean {
  const line = lines[index] ?? "";
  if (!line.trim()) return true;
  if (/^```/.test(line) || /^#{1,6}\s+/.test(line) || /^>\s?/.test(line)) return true;
  if (/^\s*(?:[-+*]|\d+\.)\s+/.test(line) || /^\s*(?:-{3,}|\*{3,}|_{3,})\s*$/.test(line)) return true;
  return index + 1 < lines.length && line.includes("|") && isTableDivider(lines[index + 1]);
}

export function MarkdownContent({ content }: { content: string }) {
  const lines = content.replace(/\r\n?/g, "\n").split("\n");
  const blocks: ReactNode[] = [];
  let index = 0;

  while (index < lines.length) {
    const line = lines[index];
    if (!line.trim()) {
      index += 1;
      continue;
    }

    const fence = line.match(/^```([^\s`]*)\s*$/);
    if (fence) {
      const code: string[] = [];
      index += 1;
      while (index < lines.length && !/^```\s*$/.test(lines[index])) {
        code.push(lines[index]);
        index += 1;
      }
      if (index < lines.length) index += 1;
      blocks.push(<pre className="markdown-code-block" key={`code-${index}`}><code data-language={fence[1] || undefined}>{code.join("\n")}</code></pre>);
      continue;
    }

    const heading = line.match(/^(#{1,6})\s+(.+)$/);
    if (heading) {
      const level = heading[1].length;
      const headingContent = inlineMarkdown(heading[2], `heading-${index}`);
      if (level === 1) blocks.push(<h1 key={`heading-${index}`}>{headingContent}</h1>);
      else if (level === 2) blocks.push(<h2 key={`heading-${index}`}>{headingContent}</h2>);
      else if (level === 3) blocks.push(<h3 key={`heading-${index}`}>{headingContent}</h3>);
      else if (level === 4) blocks.push(<h4 key={`heading-${index}`}>{headingContent}</h4>);
      else if (level === 5) blocks.push(<h5 key={`heading-${index}`}>{headingContent}</h5>);
      else blocks.push(<h6 key={`heading-${index}`}>{headingContent}</h6>);
      index += 1;
      continue;
    }

    if (/^\s*(?:-{3,}|\*{3,}|_{3,})\s*$/.test(line)) {
      blocks.push(<hr key={`hr-${index}`} />);
      index += 1;
      continue;
    }

    if (line.includes("|") && index + 1 < lines.length && isTableDivider(lines[index + 1])) {
      const headers = tableCells(line);
      const rows: string[][] = [];
      index += 2;
      while (index < lines.length && lines[index].includes("|") && lines[index].trim()) {
        rows.push(tableCells(lines[index]));
        index += 1;
      }
      blocks.push(
        <div className="markdown-table-wrap" key={`table-${index}`}>
          <table>
            <thead><tr>{headers.map((cell, cellIndex) => <th key={cellIndex}>{inlineMarkdown(cell, `table-h-${index}-${cellIndex}`)}</th>)}</tr></thead>
            <tbody>{rows.map((row, rowIndex) => <tr key={rowIndex}>{headers.map((_, cellIndex) => <td key={cellIndex}>{inlineMarkdown(row[cellIndex] ?? "", `table-${index}-${rowIndex}-${cellIndex}`)}</td>)}</tr>)}</tbody>
          </table>
        </div>,
      );
      continue;
    }

    if (/^>\s?/.test(line)) {
      const quote: string[] = [];
      while (index < lines.length && /^>\s?/.test(lines[index])) {
        quote.push(lines[index].replace(/^>\s?/, ""));
        index += 1;
      }
      blocks.push(<blockquote key={`quote-${index}`}><MarkdownContent content={quote.join("\n")} /></blockquote>);
      continue;
    }

    const listStart = line.match(/^\s*([-+*]|\d+\.)\s+(.+)$/);
    if (listStart) {
      const ordered = /\d+\./.test(listStart[1]);
      const items: string[] = [];
      const listPattern = ordered ? /^\s*\d+\.\s+(.+)$/ : /^\s*[-+*]\s+(.+)$/;
      while (index < lines.length) {
        const item = lines[index].match(listPattern);
        if (!item) break;
        items.push(item[1]);
        index += 1;
      }
      const children = items.map((item, itemIndex) => <li key={itemIndex}>{inlineMarkdown(item, `list-${index}-${itemIndex}`)}</li>);
      blocks.push(ordered ? <ol key={`list-${index}`}>{children}</ol> : <ul key={`list-${index}`}>{children}</ul>);
      continue;
    }

    const paragraph: string[] = [line];
    index += 1;
    while (index < lines.length && !isBlockStart(lines, index)) {
      paragraph.push(lines[index]);
      index += 1;
    }
    blocks.push(<p key={`paragraph-${index}`}>{inlineMarkdown(paragraph.join("\n"), `paragraph-${index}`)}</p>);
  }

  return <div className="markdown-body">{blocks}</div>;
}
