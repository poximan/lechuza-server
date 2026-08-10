import type { JsonRecord, NavigationContract } from "./models";

export class ContractParser {
  public record(value: unknown, context: string): JsonRecord {
    if (typeof value !== "object" || value === null || Array.isArray(value)) {
      throw new Error(`Contrato inválido: ${context} debe ser un objeto`);
    }
    return value as JsonRecord;
  }

  public navigation(value: unknown): NavigationContract {
    const record = this.record(value, "navigation");
    if (
      record.base_path !== "/panelexemys"
      || (record.mode !== "secure" && record.mode !== "protected")
      || typeof record.refresh_ms !== "number"
      || record.refresh_ms < 1_000
      || !Array.isArray(record.items)
    ) {
      throw new Error("Contrato inválido: navegación incompleta");
    }
    for (const [index, item] of record.items.entries()) {
      const navigationItem = this.record(item, `navigation.items[${index}]`);
      if (
        typeof navigationItem.label !== "string"
        || typeof navigationItem.href !== "string"
        || !navigationItem.href.startsWith("/panelexemys")
        || typeof navigationItem.protected !== "boolean"
      ) {
        throw new Error(`Contrato inválido: navigation.items[${index}] incompleto`);
      }
    }
    return record as unknown as NavigationContract;
  }
}
