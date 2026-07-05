// JSON-RPC provider with batch response handling
export class RPCProvider {
  private endpoint: string;
  
  constructor(endpoint: string) { this.endpoint = endpoint; }
  
  async call(method: string, params: any[]): Promise<any> {
    const resp = await fetch(this.endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ jsonrpc: "2.0", id: 1, method, params }),
    });
    const data = await resp.json();
    if (data.error) throw new Error(data.error.message);
    return data.result;
  }
  
  async batch(calls: Array<{method: string, params: any[]}>): Promise<any[]> {
    const payload = calls.map((c, i) => ({
      jsonrpc: "2.0", id: i + 1, method: c.method, params: c.params
    }));
    const resp = await fetch(this.endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const results = await resp.json();
    // Fix #161: handle batch responses — sort by id
    return results.sort((a: any, b: any) => a.id - b.id).map((r: any) => {
      if (r.error) throw new Error(r.error.message);
      return r.result;
    });
  }
}
