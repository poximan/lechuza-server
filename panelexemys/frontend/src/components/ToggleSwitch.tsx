import styles from "./ToggleSwitch.module.css";

export interface ToggleSwitchProps {
  checked: boolean;
  disabled?: boolean;
  leftLabel?: string;
  onChange: (checked: boolean) => void;
  rightLabel: string;
}

export function ToggleSwitch({
  checked,
  disabled = false,
  leftLabel,
  onChange,
  rightLabel,
}: ToggleSwitchProps) {
  return (
    <label className={styles.control}>
      {leftLabel && <span>{leftLabel}</span>}
      <input
        checked={checked}
        disabled={disabled}
        onChange={(event) => onChange(event.target.checked)}
        type="checkbox"
      />
      <i aria-hidden="true" />
      <span>{rightLabel}</span>
    </label>
  );
}
