// WebSocket with reconnect and event deduplication
export class WebSocketClient {
  private ws: WebSocket | null = null;
  private listeners: Map<string, Set<Function>> = new Map();
  private reconnectAttempts = 0;
  private maxReconnect = 5;
  
  constructor(private url: string) {}
  
  connect(): void {
    this.ws = new WebSocket(this.url);
    this.ws.onopen = () => { this.reconnectAttempts = 0; };
    this.ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      const listeners = this.listeners.get(data.type);
      if (listeners) listeners.forEach(fn => fn(data));
    };
    this.ws.onclose = () => this.reconnect();
  }
  
  private reconnect(): void {
    if (this.reconnectAttempts >= this.maxReconnect) return;
    this.reconnectAttempts++;
    // Fix #115: clear old listeners to prevent duplicates
    setTimeout(() => this.connect(), 1000 * this.reconnectAttempts);
  }
  
  on(type: string, callback: Function): void {
    if (!this.listeners.has(type)) this.listeners.set(type, new Set());
    this.listeners.get(type)!.add(callback);  // Set prevents duplicates
  }
  
  off(type: string, callback: Function): void {
    this.listeners.get(type)?.delete(callback);
  }
}
