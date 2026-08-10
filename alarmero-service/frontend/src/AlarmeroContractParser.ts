import type { Dashboard, HealthStatus, Incident } from "./AlarmModels";

export class AlarmeroContractParser {
  public parseIncidents(payload: unknown): Incident[] {
    const record = this.requireRecord(payload, "incidents");
    if (!Array.isArray(record.items)) {
      throw new Error("Contrato inválido: incidents.items debe ser una lista");
    }
    return record.items.map((item, index) => this.parseIncident(item, `incidents.items[${index}]`));
  }

  public parseDashboard(payload: unknown): Dashboard {
    const record = this.requireRecord(payload, "dashboard");
    const counts = this.requireRecord(record.counts, "dashboard.counts");
    if (!Array.isArray(record.frequent) || !Array.isArray(record.clearance)) {
      throw new Error("Contrato inválido: dashboard.frequent y dashboard.clearance deben ser listas");
    }
    return {
      counts: {
        potential: this.requireNonNegativeInteger(counts, "potential", "dashboard.counts"),
        active: this.requireNonNegativeInteger(counts, "active", "dashboard.counts"),
        recovering: this.requireNonNegativeInteger(counts, "recovering", "dashboard.counts"),
        resolved: this.requireNonNegativeInteger(counts, "resolved", "dashboard.counts"),
      },
      frequent: record.frequent.map((item, index) => {
        const entry = this.requireRecord(item, `dashboard.frequent[${index}]`);
        return {
          alarm_key: this.requireString(entry, "alarm_key", `dashboard.frequent[${index}]`),
          title: this.requireString(entry, "title", `dashboard.frequent[${index}]`),
          category: this.requireString(entry, "category", `dashboard.frequent[${index}]`),
          total: this.requireNonNegativeInteger(entry, "total", `dashboard.frequent[${index}]`),
        };
      }),
      clearance: record.clearance.map((item, index) => {
        const entry = this.requireRecord(item, `dashboard.clearance[${index}]`);
        return {
          alarm_key: this.requireString(entry, "alarm_key", `dashboard.clearance[${index}]`),
          title: this.requireString(entry, "title", `dashboard.clearance[${index}]`),
          category: this.requireString(entry, "category", `dashboard.clearance[${index}]`),
          configured_minutes: this.requireNonNegativeNumber(entry, "configured_minutes", `dashboard.clearance[${index}]`),
          sample_count: this.requireNonNegativeInteger(entry, "sample_count", `dashboard.clearance[${index}]`),
          median_minutes: this.requireNullableNonNegativeNumber(entry, "median_minutes", `dashboard.clearance[${index}]`),
          p90_minutes: this.requireNullableNonNegativeNumber(entry, "p90_minutes", `dashboard.clearance[${index}]`),
        };
      }),
    };
  }

  public parseHealth(payload: unknown): HealthStatus {
    const record = this.requireRecord(payload, "health");
    const sync = this.requireRecord(record.sync, "health.sync");
    return {
      status: this.requireEnum(record, "status", "health", ["ok", "degraded"] as const),
      generated_at: this.requireString(record, "generated_at", "health"),
      sync: {
        state: this.requireEnum(sync, "state", "health.sync", ["starting", "ok", "degraded"] as const),
        last_success_at: this.requireNullableString(sync, "last_success_at", "health.sync"),
        last_error: this.requireNullableString(sync, "last_error", "health.sync"),
      },
    };
  }

  private parseIncident(payload: unknown, path: string): Incident {
    const record = this.requireRecord(payload, path);
    return {
      incident_id: this.requireString(record, "incident_id", path),
      alarm_key: this.requireString(record, "alarm_key", path),
      title: this.requireString(record, "title", path),
      category: this.requireString(record, "category", path),
      status: this.requireEnum(record, "status", path, ["potential", "active", "recovering", "resolved"] as const),
      active: this.requireFlag(record, "active", path),
      notified: this.requireFlag(record, "notified", path),
      expected_clearance_minutes: this.requireNonNegativeNumber(record, "expected_clearance_minutes", path),
      first_seen_at: this.requireString(record, "first_seen_at", path),
      last_seen_at: this.requireString(record, "last_seen_at", path),
      qualified_at: this.requireNullableString(record, "qualified_at", path),
      notified_at: this.requireNullableString(record, "notified_at", path),
      recovery_started_at: this.requireNullableString(record, "recovery_started_at", path),
      resolved_at: this.requireNullableString(record, "resolved_at", path),
      last_event_type: this.requireString(record, "last_event_type", path),
      recipients: this.requireStringArray(record, "recipients", path),
      dispatch_status: this.requireNullableEnum(record, "dispatch_status", path, ["pending", "processing", "sent", "failed"] as const),
      dispatch_updated_at: this.requireNullableString(record, "dispatch_updated_at", path),
      dispatch_error: this.requireNullableString(record, "dispatch_error", path),
    };
  }

  private requireRecord(payload: unknown, contractName: string): Record<string, unknown> {
    if (!this.isRecord(payload)) {
      throw new Error(`Contrato inválido: ${contractName} debe ser un objeto`);
    }
    return payload;
  }

  private requireString(record: Record<string, unknown>, key: string, path: string): string {
    const value = record[key];
    if (typeof value !== "string") {
      throw new Error(`Contrato inválido: ${path}.${key} debe ser texto`);
    }
    return value;
  }

  private requireNullableString(record: Record<string, unknown>, key: string, path: string): string | null {
    const value = record[key];
    if (value === null) return null;
    if (typeof value !== "string") {
      throw new Error(`Contrato inválido: ${path}.${key} debe ser texto o null`);
    }
    return value;
  }

  private requireNonNegativeNumber(record: Record<string, unknown>, key: string, path: string): number {
    const value = record[key];
    if (typeof value !== "number" || !Number.isFinite(value) || value < 0) {
      throw new Error(`Contrato inválido: ${path}.${key} debe ser un número no negativo`);
    }
    return value;
  }

  private requireNullableNonNegativeNumber(record: Record<string, unknown>, key: string, path: string): number | null {
    if (record[key] === null) return null;
    return this.requireNonNegativeNumber(record, key, path);
  }

  private requireNonNegativeInteger(record: Record<string, unknown>, key: string, path: string): number {
    const value = this.requireNonNegativeNumber(record, key, path);
    if (!Number.isInteger(value)) {
      throw new Error(`Contrato inválido: ${path}.${key} debe ser entero`);
    }
    return value;
  }

  private requireFlag(record: Record<string, unknown>, key: string, path: string): number {
    const value = this.requireNonNegativeInteger(record, key, path);
    if (value !== 0 && value !== 1) {
      throw new Error(`Contrato inválido: ${path}.${key} debe ser 0 o 1`);
    }
    return value;
  }

  private requireStringArray(record: Record<string, unknown>, key: string, path: string): string[] {
    const value = record[key];
    if (!Array.isArray(value) || !value.every((item) => typeof item === "string")) {
      throw new Error(`Contrato inválido: ${path}.${key} debe ser una lista de textos`);
    }
    return value;
  }

  private requireEnum<const T extends readonly string[]>(
    record: Record<string, unknown>, key: string, path: string, allowed: T,
  ): T[number] {
    const value = record[key];
    if (typeof value !== "string" || !allowed.includes(value)) {
      throw new Error(`Contrato inválido: ${path}.${key} no es un valor permitido`);
    }
    return value as T[number];
  }

  private requireNullableEnum<const T extends readonly string[]>(
    record: Record<string, unknown>, key: string, path: string, allowed: T,
  ): T[number] | null {
    if (record[key] === null) return null;
    return this.requireEnum(record, key, path, allowed);
  }

  private isRecord(value: unknown): value is Record<string, unknown> {
    return typeof value === "object" && value !== null && !Array.isArray(value);
  }
}
