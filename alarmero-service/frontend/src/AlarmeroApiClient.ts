import { AlarmeroContractParser } from "./AlarmeroContractParser";
import type { Dashboard, HealthStatus, Incident, IncidentFilter } from "./AlarmModels";

export class AlarmeroApiClient {
  public constructor(
    private readonly baseUrl: URL,
    private readonly parser = new AlarmeroContractParser(),
  ) {}

  public async getIncidents(filter: IncidentFilter, signal?: AbortSignal): Promise<Incident[]> {
    const payload = await this.getJson(`api/incidents?filter=${encodeURIComponent(filter)}&limit=1000`, signal);
    return this.parser.parseIncidents(payload);
  }

  public async getDashboard(signal?: AbortSignal): Promise<Dashboard> {
    return this.parser.parseDashboard(await this.getJson("api/dashboard", signal));
  }

  public async getHealth(signal?: AbortSignal): Promise<HealthStatus> {
    return this.parser.parseHealth(await this.getJson("health", signal));
  }

  private async getJson(relativePath: string, signal?: AbortSignal): Promise<unknown> {
    const response = await fetch(new URL(relativePath, this.baseUrl), {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
      signal,
    });
    if (!response.ok) {
      throw new Error(`${relativePath} respondió HTTP ${response.status}`);
    }
    return response.json() as Promise<unknown>;
  }
}
