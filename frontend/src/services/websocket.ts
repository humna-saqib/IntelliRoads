import type { TrafficSnapshot } from '../types/traffic';

type MessageCallback    = (data: TrafficSnapshot) => void;
type ConnectCallback    = () => void;
type DisconnectCallback = () => void;

const MAX_RETRIES        = 5;
const BASE_BACKOFF_MS    = 1000;

export class TrafficWebSocket {
  private url:            string;
  private onMessage:      MessageCallback;
  private onConnect:      ConnectCallback;
  private onDisconnect:   DisconnectCallback;
  private ws:             WebSocket | null = null;
  private retryCount:     number = 0;
  private retryTimer:     ReturnType<typeof setTimeout> | null = null;
  private shouldReconnect: boolean = true;
  private _isConnected:   boolean = false;

  constructor(
    url: string,
    onMessage: MessageCallback,
    onConnect: ConnectCallback,
    onDisconnect: DisconnectCallback,
  ) {
    this.url          = url;
    this.onMessage    = onMessage;
    this.onConnect    = onConnect;
    this.onDisconnect = onDisconnect;
  }

  connect(): void {
    if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) {
      return;
    }
    try {
      this.ws = new WebSocket(this.url);

      this.ws.onopen = () => {
        this._isConnected = true;
        this.retryCount   = 0;
        this.onConnect();
      };

      this.ws.onmessage = (event: MessageEvent) => {
        try {
          const data = JSON.parse(event.data as string) as TrafficSnapshot;
          this.onMessage(data);
        } catch (err) {
          console.error('[TrafficWebSocket] Failed to parse message:', err);
        }
      };

      this.ws.onerror = (err) => {
        console.error('[TrafficWebSocket] WebSocket error:', err);
      };

      this.ws.onclose = () => {
        this._isConnected = false;
        this.onDisconnect();
        if (this.shouldReconnect && this.retryCount < MAX_RETRIES) {
          const delay = BASE_BACKOFF_MS * Math.pow(2, this.retryCount);
          console.log(`[TrafficWebSocket] Reconnecting in ${delay}ms (attempt ${this.retryCount + 1}/${MAX_RETRIES})`);
          this.retryTimer = setTimeout(() => {
            this.retryCount++;
            this.connect();
          }, delay);
        } else if (this.retryCount >= MAX_RETRIES) {
          console.warn('[TrafficWebSocket] Max reconnect attempts reached. Giving up.');
        }
      };
    } catch (err) {
      console.error('[TrafficWebSocket] Failed to create WebSocket:', err);
    }
  }

  disconnect(): void {
    this.shouldReconnect = false;
    if (this.retryTimer) {
      clearTimeout(this.retryTimer);
      this.retryTimer = null;
    }
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
    this._isConnected = false;
  }

  isConnected(): boolean {
    return this._isConnected && this.ws?.readyState === WebSocket.OPEN;
  }
}
