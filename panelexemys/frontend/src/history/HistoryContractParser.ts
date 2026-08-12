import type { JsonRecord, JsonValue } from "../models";
import type {
  ConnectionHistory,
  ConnectionHistoryEvent,
} from "./HistoryModels";

export class HistoryContractParser {
  public parse(value: JsonRecord): ConnectionHistory {
    const rangeStartIso = this.requiredString(
      value.range_start,
      "history.range_start",
    );
    const rangeEndIso = this.requiredString(
      value.range_end,
      "history.range_end",
    );
    const rangeStart = this.instant(rangeStartIso, "history.range_start");
    const rangeEnd = this.instant(rangeEndIso, "history.range_end");
    if (rangeEnd.getTime() <= rangeStart.getTime()) {
      throw new Error("Contrato inválido: el rango histórico no es creciente");
    }
    const connectedBefore = this.connectedOrNull(
      value.connected_before,
      "history.connected_before",
    );
    const totalPeriods = this.nonNegativeInteger(
      value.total_periods,
      "history.total_periods",
    );
    if (!Array.isArray(value.data)) {
      throw new Error("Contrato inválido: history.data debe ser una lista");
    }
    const events = value.data.map((item, index) => this.event(item, index));
    events.sort(
      (left, right) => left.instant.getTime() - right.instant.getTime(),
    );
    return {
      connectedBefore,
      events,
      rangeEnd,
      rangeEndIso,
      rangeStart,
      rangeStartIso,
      totalPeriods,
    };
  }

  private event(value: JsonValue, index: number): ConnectionHistoryEvent {
    if (typeof value !== "object" || value === null || Array.isArray(value)) {
      throw new Error(
        `Contrato inválido: history.data[${index}] debe ser un objeto`,
      );
    }
    const timestamp = this.requiredString(
      value.timestamp,
      `history.data[${index}].timestamp`,
    );
    return {
      connected: this.connected(
        value.conectado,
        `history.data[${index}].conectado`,
      ),
      instant: this.instant(timestamp, `history.data[${index}].timestamp`),
      timestamp,
    };
  }

  private connected(value: JsonValue | undefined, context: string): 0 | 1 {
    if (value !== 0 && value !== 1)
      throw new Error(`Contrato inválido: ${context} debe ser 0 o 1`);
    return value;
  }

  private connectedOrNull(
    value: JsonValue | undefined,
    context: string,
  ): 0 | 1 | null {
    if (value === null) return null;
    return this.connected(value, context);
  }

  private instant(value: string, context: string): Date {
    const instant = new Date(value);
    if (Number.isNaN(instant.getTime()))
      throw new Error(`Contrato inválido: ${context} no es ISO-8601`);
    return instant;
  }

  private nonNegativeInteger(
    value: JsonValue | undefined,
    context: string,
  ): number {
    if (typeof value !== "number" || !Number.isInteger(value) || value < 0) {
      throw new Error(
        `Contrato inválido: ${context} debe ser un entero no negativo`,
      );
    }
    return value;
  }

  private requiredString(
    value: JsonValue | undefined,
    context: string,
  ): string {
    if (typeof value !== "string" || value.length === 0) {
      throw new Error(`Contrato inválido: ${context} debe ser texto`);
    }
    return value;
  }
}
