import { Button } from "@servicoop/frontend-foundation";

import type { IncidentFilter } from "../AlarmModels";
import styles from "./FilterBar.module.css";

export interface FilterBarProps {
  selected: IncidentFilter;
  onSelect: (filter: IncidentFilter) => void;
}

export function FilterBar({ onSelect, selected }: FilterBarProps) {
  const options: ReadonlyArray<[IncidentFilter, string]> = [
    ["potential", "Potenciales"], ["active", "Activas"], ["all", "Todas"],
  ];
  return (
    <div className={styles.filters} role="group" aria-label="Filtro de incidencias">
      {options.map(([value, label]) => (
        <Button
          aria-pressed={selected === value}
          key={value}
          onClick={() => onSelect(value)}
          variant={selected === value ? "primary" : "ghost"}
        >
          {label}
        </Button>
      ))}
    </div>
  );
}
