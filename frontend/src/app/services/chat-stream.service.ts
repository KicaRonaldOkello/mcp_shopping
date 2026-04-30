import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

export type ChatSseEvent =
  | { type: 'meta'; threadId: string }
  | { type: 'step'; node: string }
  | { type: 'token'; text: string }
  | { type: 'done' }
  | { type: 'error'; message: string };

function parseOneBlock(block: string): ChatSseEvent | null {
  const lines = block.split(/\r?\n/).filter((l) => l.length > 0);
  let eventName = 'message';
  let dataLine = '';
  for (const line of lines) {
    if (line.startsWith('event:')) {
      eventName = line.slice(6).trim();
    } else if (line.startsWith('data:')) {
      dataLine += line.slice(5).trim();
    }
  }
  if (!dataLine) {
    return null;
  }
  let payload: Record<string, unknown>;
  try {
    payload = JSON.parse(dataLine) as Record<string, unknown>;
  } catch {
    return { type: 'error', message: 'Invalid SSE payload' };
  }
  switch (eventName) {
    case 'meta':
      return { type: 'meta', threadId: String(payload['thread_id'] ?? '') };
    case 'step':
      return { type: 'step', node: String(payload['node'] ?? '') };
    case 'token':
      return { type: 'token', text: String(payload['text'] ?? '') };
    case 'done':
      return { type: 'done' };
    case 'error':
      return { type: 'error', message: String(payload['message'] ?? 'Unknown error') };
    default:
      return null;
  }
}

function drainSseBuffer(buffer: string): { events: ChatSseEvent[]; buffer: string } {
  const events: ChatSseEvent[] = [];
  let sep: number;
  while ((sep = buffer.indexOf('\n\n')) >= 0) {
    const block = buffer.slice(0, sep);
    buffer = buffer.slice(sep + 2);
    const evt = parseOneBlock(block);
    if (evt) {
      events.push(evt);
    }
  }
  return { events, buffer };
}

async function extractErrorMessage(res: Response): Promise<string> {
  const contentType = res.headers.get('content-type') ?? '';
  const text = (await res.text()).trim();

  if (!text) {
    return `HTTP ${res.status}`;
  }

  if (contentType.includes('application/json')) {
    try {
      const payload = JSON.parse(text) as Record<string, unknown>;
      const detail = payload['detail'];
      if (typeof detail === 'string' && detail.trim()) {
        return detail;
      }
      const message = payload['message'];
      if (typeof message === 'string' && message.trim()) {
        return message;
      }
    } catch {
      // Fall back to the raw response text below.
    }
  }

  return text;
}

@Injectable({ providedIn: 'root' })
export class ChatStreamService {
  streamMessage(message: string, threadId?: string | null): Observable<ChatSseEvent> {
    return new Observable((subscriber) => {
      const controller = new AbortController();
      const run = async (): Promise<void> => {
        try {
          const res = await fetch('/api/chat/stream', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              Accept: 'text/event-stream',
            },
            body: JSON.stringify({
              message,
              thread_id: threadId ?? undefined,
            }),
            signal: controller.signal,
          });
          if (!res.ok) {
            throw new Error(await extractErrorMessage(res));
          }
          const reader = res.body?.getReader();
          if (!reader) {
            throw new Error('No response body');
          }
          const decoder = new TextDecoder();
          let buffer = '';
          while (true) {
            const { done, value } = await reader.read();
            if (done) {
              break;
            }
            buffer += decoder.decode(value, { stream: true });
            const drained = drainSseBuffer(buffer);
            buffer = drained.buffer;
            for (const ev of drained.events) {
              subscriber.next(ev);
            }
          }
          const final = drainSseBuffer(buffer + '\n\n');
          for (const ev of final.events) {
            subscriber.next(ev);
          }
          subscriber.complete();
        } catch (err) {
          if ((err as Error).name === 'AbortError') {
            subscriber.complete();
            return;
          }
          subscriber.error(err);
        }
      };
      void run();
      return () => controller.abort();
    });
  }
}
