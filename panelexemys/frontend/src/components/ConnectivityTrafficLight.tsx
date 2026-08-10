import styles from "./ConnectivityTrafficLight.module.css";

export interface ConnectivityTrafficLightProps {
  percentage: number;
  redBelow: number;
  yellowBelow: number;
}

export function ConnectivityTrafficLight({
  percentage,
  redBelow,
  yellowBelow,
}: ConnectivityTrafficLightProps) {
  const active =
    percentage >= yellowBelow
      ? "green"
      : percentage >= redBelow
        ? "yellow"
        : "red";
  const label =
    active === "green"
      ? "Normal"
      : active === "yellow"
        ? "Advertencia"
        : "Crítico";
  return (
    <div
      aria-label={`Salud de conexión: ${label}`}
      className={styles.wrapper}
      role="status"
    >
      <div className={styles.housing}>
        <i
          className={`${styles.light} ${styles.red} ${active === "red" ? styles.active : ""}`}
        />
        <i
          className={`${styles.light} ${styles.yellow} ${active === "yellow" ? styles.active : ""}`}
        />
        <i
          className={`${styles.light} ${styles.green} ${active === "green" ? styles.active : ""}`}
        />
      </div>
      <strong>{label}</strong>
    </div>
  );
}
