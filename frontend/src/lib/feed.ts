import type { ClientCmd, Feed, FeedStatus, ServerMsg } from '../types';
import { CONFIG } from '../config';
import { SimFeed } from './simulator';

/** Real backend: one WebSocket that carries ServerMsg JSON down and ClientCmd JSON up. */
class WsFeed implements Feed {
  label: string;
  private ws: WebSocket | null = null;
  private stopped = false;
  private retry: ReturnType<typeof setTimeout> | undefined;
  private attempts = 0;

  constructor(private url: string) {
    this.label = `Live backend, ${url}`;
  }

  start(onMsg: (m: ServerMsg) => void, onStatus: (s: FeedStatus) => void): void {
    this.stopped = false;
    const open = () => {
      onStatus(this.attempts === 0 ? 'connecting' : 'reconnecting');
      const ws = new WebSocket(this.url);
      this.ws = ws;
      ws.onopen = () => {
        this.attempts = 0;
        onStatus('live');
      };
      ws.onmessage = (e) => {
        try {
          onMsg(JSON.parse(e.data as string) as ServerMsg);
        } catch {
          /* ignore malformed frame */
        }
      };
      ws.onclose = () => {
        if (this.stopped) return;
        this.attempts += 1;
        onStatus(this.attempts >= 5 ? 'offline' : 'reconnecting');
        const delay = Math.min(15000, 1000 * 2 ** Math.min(this.attempts, 4));
        this.retry = setTimeout(open, delay);
      };
      ws.onerror = () => ws.close();
    };
    open();
  }

  stop(): void {
    this.stopped = true;
    if (this.retry) clearTimeout(this.retry);
    this.ws?.close();
  }

  send(cmd: ClientCmd): void {
    if (this.ws?.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify(cmd));
  }
}

export const feed: Feed = CONFIG.wsUrl ? new WsFeed(CONFIG.wsUrl) : new SimFeed();
