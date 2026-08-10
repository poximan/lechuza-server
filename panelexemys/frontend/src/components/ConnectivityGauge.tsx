import styles from "./ConnectivityGauge.module.css";

export interface ConnectivityGaugeProps {
  percentage: number;
  redBelow: number;
  yellowBelow: number;
}

export function ConnectivityGauge({
  percentage,
  redBelow,
  yellowBelow,
}: ConnectivityGaugeProps) {
  const value = Math.max(0, Math.min(100, percentage));
  const angle = -90 + value * 1.8;
  return (
    <div
      aria-label={`Grado de conectividad ${value.toFixed(1)} por ciento`}
      className={styles.gauge}
      role="meter"
      aria-valuemax={100}
      aria-valuemin={0}
      aria-valuenow={value}
    >
      <svg viewBox="0 0 220 132">
        <path
          className={styles.base}
          d="M20 112 A90 90 0 0 1 200 112"
          pathLength="100"
        />
        <path
          className={styles.red}
          d="M20 112 A90 90 0 0 1 200 112"
          pathLength="100"
          strokeDasharray={`${redBelow} ${100 - redBelow}`}
        />
        <path
          className={styles.yellow}
          d="M20 112 A90 90 0 0 1 200 112"
          pathLength="100"
          strokeDasharray={`${yellowBelow - redBelow} ${100 - yellowBelow + redBelow}`}
          strokeDashoffset={-redBelow}
        />
        <path
          className={styles.green}
          d="M20 112 A90 90 0 0 1 200 112"
          pathLength="100"
          strokeDasharray={`${100 - yellowBelow} ${yellowBelow}`}
          strokeDashoffset={-yellowBelow}
        />
        <line
          className={styles.needle}
          transform={`rotate(${angle} 110 112)`}
          x1="110"
          x2="110"
          y1="112"
          y2="40"
        />
        <circle className={styles.hub} cx="110" cy="112" r="8" />
      </svg>
      <strong>{value.toFixed(1)}%</strong>
    </div>
  );
}
