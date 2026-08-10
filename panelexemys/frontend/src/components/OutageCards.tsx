import { UtcMinusThreePresenter } from "@servicoop/frontend-foundation";
import { useMemo } from "react";

import type { JsonValue } from "../models";
import styles from "./OutageCards.module.css";

export function OutageCards({ value }: { value: JsonValue | undefined }) {
  const presenter = useMemo(() => new UtcMinusThreePresenter(), []);
  try {
    if (
      typeof value !== "object" ||
      value === null ||
      Array.isArray(value) ||
      !Array.isArray(value.items)
    ) {
      throw new Error("outages debe incluir items");
    }
    if (value.items.length === 0)
      return (
        <p className={styles.empty}>
          No hay caídas registradas para el GRD seleccionado.
        </p>
      );
    return (
      <div className={styles.grid}>
        {value.items.slice(0, 10).map((item, index) => {
          if (typeof item !== "object" || item === null || Array.isArray(item))
            throw new Error(`outages.items[${index}] debe ser un objeto`);
          if (
            typeof item.start_timestamp !== "string" ||
            typeof item.duration_minutes !== "number"
          )
            throw new Error(`outages.items[${index}] incompleto`);
          return (
            <article
              className={styles.card}
              key={`${item.start_timestamp}-${index}`}
            >
              <strong>Caída {index + 1}</strong>
              <span>
                Inicio {presenter.formatInstant(item.start_timestamp)}
              </span>
              <span>Duración {Math.trunc(item.duration_minutes)} min</span>
            </article>
          );
        })}
      </div>
    );
  } catch (reason) {
    return (
      <p className={styles.error} role="alert">
        Contrato inválido:{" "}
        {reason instanceof Error ? reason.message : String(reason)}
      </p>
    );
  }
}
