import type { JsonRecord, JsonValue } from "../models";

export class JsonContractReader {
  public record(value: JsonValue | undefined, context: string): JsonRecord {
    if (typeof value !== "object" || value === null || Array.isArray(value)) {
      throw new Error(`Contrato inválido: ${context} debe ser un objeto`);
    }
    return value;
  }

  public records(value: JsonValue | undefined, context: string): JsonRecord[] {
    if (!Array.isArray(value)) {
      throw new Error(`Contrato inválido: ${context} debe ser una lista`);
    }
    return value.map((item, index) =>
      this.record(item, `${context}[${index}]`),
    );
  }

  public string(value: JsonValue | undefined, context: string): string {
    if (typeof value !== "string") {
      throw new Error(`Contrato inválido: ${context} debe ser texto`);
    }
    return value;
  }

  public number(value: JsonValue | undefined, context: string): number {
    if (typeof value !== "number" || !Number.isFinite(value)) {
      throw new Error(`Contrato inválido: ${context} debe ser numérico`);
    }
    return value;
  }

  public boolean(value: JsonValue | undefined, context: string): boolean {
    if (typeof value !== "boolean") {
      throw new Error(`Contrato inválido: ${context} debe ser booleano`);
    }
    return value;
  }

  public optionalRecord(
    value: JsonValue | undefined,
    context: string,
  ): JsonRecord | null {
    return value === null || value === undefined
      ? null
      : this.record(value, context);
  }

  public optionalString(
    value: JsonValue | undefined,
    context: string,
  ): string | null {
    if (value === null || value === undefined || value === "") return null;
    return this.string(value, context);
  }

  public optionalNumber(
    value: JsonValue | undefined,
    context: string,
  ): number | null {
    if (value === null || value === undefined) return null;
    return this.number(value, context);
  }
}
