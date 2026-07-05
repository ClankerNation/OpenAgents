// Session manager with 401 auto-refresh
export class SessionManager {
  private token: string = "";
  private refreshToken: string = "";
  
  async handle401(response: Response): Promise<Response> {
    if (response.status === 401 && this.refreshToken) {
      const refreshResp = await fetch("/api/auth/refresh", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: this.refreshToken }),
      });
      if (refreshResp.ok) {
        const { token, refresh_token } = await refreshResp.json();
        this.token = token;
        this.refreshToken = refresh_token;
        // Retry original request with new token
        return fetch(response.url, { headers: { Authorization: `Bearer ${token}` } });
      }
    }
    return response;
  }
}
