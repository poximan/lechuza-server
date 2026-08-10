import { ContractParser } from "./ContractParser";
import type { JsonRecord, NavigationContract } from "./models";

export class PanelexemysApiClient {
  public constructor(private readonly parser = new ContractParser()) {}

  public async navigation(signal?: AbortSignal): Promise<NavigationContract> {
    return this.parser.navigation(await this.get("navigation", signal));
  }

  public async page(name: string, signal?: AbortSignal): Promise<JsonRecord> {
    return this.parser.record(await this.get(name, signal), name);
  }

  public async grd(grdId: number, windowName: string, page: number, signal?: AbortSignal): Promise<JsonRecord> {
    const query = new URLSearchParams({ grd_id: String(grdId), window: windowName, page: String(page) });
    return this.parser.record(await this.get(`grd?${query}`, signal), "grd");
  }

  public async setRelesObserver(enabled: boolean): Promise<JsonRecord> {
    return this.parser.record(await this.send("reles/observer", "PUT", { enabled }), "reles observer");
  }

  public async setBrokerConnection(enabled: boolean): Promise<JsonRecord> {
    return this.parser.record(await this.send("broker/connection", "PUT", { enabled }), "broker connection");
  }

  public async sendTestEmail(): Promise<JsonRecord> {
    return this.parser.record(await this.send("email/test", "POST", {}), "email test");
  }

  private async get(path: string, signal?: AbortSignal): Promise<unknown> {
    const response = await fetch(new URL(`api/${path}`, document.baseURI), {
      cache: "no-store",
      credentials: "same-origin",
      headers: { Accept: "application/json" },
      signal,
    });
    return this.read(response, path);
  }

  private async send(path: string, method: "POST" | "PUT", body: unknown): Promise<unknown> {
    const response = await fetch(new URL(`api/${path}`, document.baseURI), {
      body: JSON.stringify(body),
      credentials: "same-origin",
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      method,
    });
    return this.read(response, path);
  }

  private async read(response: Response, context: string): Promise<unknown> {
    const payload = await response.json().catch(() => null);
    if (!response.ok) {
      const detail = typeof payload === "object" && payload !== null && "error" in payload
        ? String((payload as { error: unknown }).error)
        : `HTTP ${response.status}`;
      throw new Error(`${context}: ${detail}`);
    }
    return payload;
  }
}
