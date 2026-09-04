import { Card } from "@servicoop/frontend-foundation";
import { useEffect } from "react";

import { JsonContractReader } from "../contracts/JsonContractReader";
import type { JsonRecord } from "../models";
import styles from "./Pages.module.css";

const reader = new JsonContractReader();

interface BreakerState {
  bit: 0 | 1 | null;
  state: string;
}

interface GeneratorState {
  unsafe: boolean;
  error: string | null;
  group: BreakerState;
  line: BreakerState;
  summary: string;
}

function breaker(value: unknown, context: string): BreakerState {
  const item = reader.record(value as never, context);
  const state = reader.string(item.estado, `${context}.estado`).toLowerCase();
  if (item.bit === null && (state === "incierto" || state === "desconocido"))
    return { bit: null, state };
  if (
    (item.bit !== 0 && item.bit !== 1) ||
    state !== (item.bit === 1 ? "cerrado" : "abierto")
  ) {
    throw new Error(
      `Contrato inválido: ${context} no coincide entre bit y estado`,
    );
  }
  return { bit: item.bit, state };
}

function Breaker({
  x,
  state,
  label,
}: {
  x: number;
  state: BreakerState;
  label: string;
}) {
  const color =
    state.bit === null ? "#64748b" : state.bit === 1 ? "#c62828" : "#2e7d32";
  return (
    <g>
      <circle
        cx={x}
        cy="172"
        fill="white"
        r="8"
        stroke="#334155"
        strokeWidth="4"
      />
      <circle
        cx={x}
        cy="244"
        fill="white"
        r="8"
        stroke="#334155"
        strokeWidth="4"
      />
      {state.bit === 1 ? (
        <line
          stroke={color}
          strokeLinecap="round"
          strokeWidth="7"
          x1={x}
          x2={x}
          y1="172"
          y2="244"
        />
      ) : (
        <line
          stroke={color}
          strokeDasharray={state.bit === null ? "7 7" : undefined}
          strokeLinecap="round"
          strokeWidth="7"
          x1={x}
          x2={x + 34}
          y1="172"
          y2="214"
        />
      )}
      <text fontSize="16" fontWeight="800" x={x - 30} y="214">
        {label}
      </text>
    </g>
  );
}

function GeneratorDiagram({
  line,
  group,
  unsafe,
}: {
  line: BreakerState;
  group: BreakerState;
  unsafe: boolean;
}) {
  return (
    <svg
      aria-label="Diagrama unifilar del generador"
      className={styles.diagram}
      role="img"
      viewBox="0 0 760 560"
    >
      <rect
        className={styles.diagramNode}
        height="558"
        rx="10"
        width="758"
        x="1"
        y="1"
      />
      <text fontSize="18" fontWeight="700" textAnchor="middle" x="245" y="48">
        Red externa
      </text>
      <path
        className={styles.diagramWire}
        d="M215 96h60m-47 16 13-32m4 32 13-32m4 32 13-32M245 96v76"
      />
      <text fontSize="18" fontWeight="700" textAnchor="middle" x="515" y="48">
        Grupo electrógeno
      </text>
      <circle
        cx="515"
        cy="102"
        fill="#fff8df"
        r="32"
        stroke="#334155"
        strokeWidth="4"
      />
      <text fontSize="32" fontWeight="800" textAnchor="middle" x="515" y="113">
        G
      </text>
      <line
        className={styles.diagramWire}
        x1="515"
        x2="515"
        y1="134"
        y2="172"
      />
      <Breaker label="IL" state={line} x={245} />
      <Breaker label="IG" state={group} x={515} />
      <path className={styles.diagramWire} d="M245 244v110m270-110v110" />
      <line
        className={styles.diagramBus}
        stroke={unsafe ? "#c62828" : undefined}
        x1="205"
        x2="555"
        y1="354"
        y2="354"
      />
      <text fontSize="15" fontWeight="700" textAnchor="middle" x="382" y="337">
        Barra
      </text>
      <line
        className={styles.diagramWire}
        x1="382"
        x2="382"
        y1="354"
        y2="432"
      />
      <rect
        className={styles.diagramNode}
        height="54"
        rx="6"
        width="144"
        x="310"
        y="432"
      />
      <text fontSize="18" fontWeight="700" textAnchor="middle" x="382" y="466">
        Carga
      </text>
    </svg>
  );
}

function generatorState(value: JsonRecord, title: string): GeneratorState {
  return {
    unsafe: reader.boolean(value.unsafe_state, `${title}.unsafe_state`),
    error: reader.optionalString(value.error, `${title}.error`),
    line: breaker(value.interruptor_linea, `${title}.interruptor_linea`),
    group: breaker(value.interruptor_grupo, `${title}.interruptor_grupo`),
    summary: reader.string(value.summary, `${title}.summary`),
  };
}

function GeneratorCard({
  state: { unsafe, error, group, line, summary },
  title,
}: {
  state: GeneratorState;
  title: string;
}) {
  return (
    <Card className={`${styles.card} ${unsafe ? styles.unsafeCard : ""}`}>
      <div className={styles.cardHeader}>
        <h2>{title}</h2>
      </div>
      {error && <p className={styles.error}>{error}</p>}
      <GeneratorDiagram unsafe={unsafe} group={group} line={line} />
      <div className={styles.statusRow}>
        <div
          className={`${styles.generatorStateChip} ${line.bit === 1 ? styles.generatorStateClosed : line.bit === 0 ? styles.generatorStateOpen : styles.generatorStateUnknown}`}
        >
          Línea: interruptor {line.state}
        </div>
        <div
          className={`${styles.generatorStateChip} ${group.bit === 1 ? styles.generatorStateClosed : group.bit === 0 ? styles.generatorStateOpen : styles.generatorStateUnknown}`}
        >
          Grupo: interruptor {group.state}
        </div>
      </div>
      <p>
        <strong>{summary}</strong>
      </p>
    </Card>
  );
}

export function GeneratorsPage({
  data,
  onAttentionChange,
}: {
  data: JsonRecord;
  onAttentionChange: (active: boolean) => void;
}) {
  const estivariz = reader.record(data.estivariz, "generadores.estivariz");
  const fontana = reader.record(data.fontana, "generadores.fontana");
  const estivarizState = generatorState(estivariz, "edificio estivariz");
  const fontanaState = generatorState(fontana, "edificio fontana");
  const hasUnsafeGeneratorState = estivarizState.unsafe || fontanaState.unsafe;

  useEffect(() => {
    onAttentionChange(hasUnsafeGeneratorState);
    return () => onAttentionChange(false);
  }, [hasUnsafeGeneratorState, onAttentionChange]);

  return (
    <div className={styles.generatorsGrid}>
      <GeneratorCard
        state={estivarizState}
        title="edificio estivariz"
      />
      <GeneratorCard
        state={fontanaState}
        title="edificio fontana"
      />
    </div>
  );
}
