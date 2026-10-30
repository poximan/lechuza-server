import { flowTimeUnit, flowUnitLabel, flowVolumeUnit } from "./FlowUnits";
import type { FlowTimeUnit, FlowVolumeUnit } from "./FlowUnits";
import styles from "./FlowMetersPage.module.css";

export function FlowUnitControls({ volume, period, disabled, onVolumeChange, onPeriodChange }: {
  volume: FlowVolumeUnit;
  period: FlowTimeUnit;
  disabled: boolean;
  onVolumeChange: (value: FlowVolumeUnit) => void;
  onPeriodChange: (value: FlowTimeUnit) => void;
}) {
  return <div className={styles.controls} role="group" aria-label="Unidad de caudal">
    <strong>Unidad de caudal</strong>
    <label>Volumen
      <select disabled={disabled} value={volume} onChange={event => onVolumeChange(flowVolumeUnit(event.target.value))}>
        <option value="l">Litro (l)</option>
        <option value="m3">Metro cúbico (m³)</option>
      </select>
    </label>
    <label>Tiempo
      <select disabled={disabled} value={period} onChange={event => onPeriodChange(flowTimeUnit(event.target.value))}>
        <option value="s">Segundo</option>
        <option value="h">Hora</option>
        <option value="d">Día</option>
      </select>
    </label>
    <span className={styles.muted}>{flowUnitLabel(volume, period)}</span>
  </div>;
}
