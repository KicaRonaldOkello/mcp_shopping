import { CommonModule } from '@angular/common';
import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Subscription } from 'rxjs';

import { FormatMeridianReplyPipe } from '../pipes/format-meridian-reply.pipe';
import { ChatStreamService } from '../services/chat-stream.service';

@Component({
  selector: 'app-chat',
  standalone: true,
  imports: [CommonModule, FormsModule, FormatMeridianReplyPipe],
  templateUrl: './chat.component.html',
  styleUrl: './chat.component.scss',
})
export class ChatComponent {
  private readonly chat = inject(ChatStreamService);

  readonly messages = signal<{ role: 'user' | 'assistant'; content: string }[]>([]);
  draft = '';
  readonly streaming = signal('');
  readonly busy = signal(false);
  readonly lastNode = signal('');

  private threadId: string | null = null;
  private streamSub: Subscription | null = null;

  send(): void {
    const text = this.draft.trim();
    if (!text || this.busy()) {
      return;
    }
    this.draft = '';
    this.messages.update((m) => [...m, { role: 'user', content: text }]);
    this.streaming.set('');
    this.lastNode.set('');
    this.busy.set(true);
    this.streamSub?.unsubscribe();

    this.streamSub = this.chat.streamMessage(text, this.threadId).subscribe({
      next: (ev) => {
        if (ev.type === 'meta') {
          this.threadId = ev.threadId;
        } else if (ev.type === 'step') {
          this.lastNode.set(ev.node);
        } else if (ev.type === 'token') {
          this.streaming.update((s) => s + ev.text);
        } else if (ev.type === 'done') {
          this.flushAssistant();
        } else if (ev.type === 'error') {
          this.messages.update((m) => [...m, { role: 'assistant', content: `Error: ${ev.message}` }]);
          this.streaming.set('');
          this.busy.set(false);
        }
      },
      error: (err: Error) => {
        this.messages.update((m) => [
          ...m,
          { role: 'assistant', content: `Error: ${err?.message ?? String(err)}` },
        ]);
        this.streaming.set('');
        this.busy.set(false);
      },
      complete: () => {
        if (this.busy()) {
          this.flushAssistant();
        }
      },
    });
  }

  private flushAssistant(): void {
    const s = this.streaming();
    if (s) {
      this.messages.update((m) => [...m, { role: 'assistant', content: s }]);
    }
    this.streaming.set('');
    this.busy.set(false);
  }
}
