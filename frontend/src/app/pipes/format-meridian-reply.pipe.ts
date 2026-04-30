import { Pipe, PipeTransform } from '@angular/core';

/**
 * MCP / tool results often arrive as JSON inside ```json fences, e.g.
 * `[{ "type": "text", "text": "Found 200 products:\\n\\n..." }]`.
 * This pipe unwraps that into plain text for the chat UI.
 */
@Pipe({
  name: 'formatMeridianReply',
  standalone: true,
})
export class FormatMeridianReplyPipe implements PipeTransform {
  transform(value: string | null | undefined): string {
    if (value == null || value === '') {
      return '';
    }
    return value.replace(/```(?:json)?\s*([\s\S]*?)```/gi, (_full, inner: string) => {
      const trimmed = inner.trim();
      if (!trimmed) {
        return '';
      }
      try {
        const parsed: unknown = JSON.parse(trimmed);
        const human = extractHumanText(parsed);
        if (human !== null) {
          return human;
        }
        return JSON.stringify(parsed, null, 2);
      } catch {
        return trimmed;
      }
    });
  }
}

function extractHumanText(parsed: unknown): string | null {
  if (Array.isArray(parsed)) {
    const chunks: string[] = [];
    for (const item of parsed) {
      if (!item || typeof item !== 'object') {
        continue;
      }
      const o = item as Record<string, unknown>;
      if (o['type'] === 'text' && typeof o['text'] === 'string') {
        chunks.push(o['text']);
      }
    }
    if (chunks.length > 0) {
      return chunks.join('\n\n');
    }
  }
  if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
    const o = parsed as Record<string, unknown>;
    if (o['type'] === 'text' && typeof o['text'] === 'string') {
      return o['text'];
    }
  }
  return null;
}
