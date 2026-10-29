import type { KeyboardEvent } from "react";

import type { NavigationItem } from "../models";
import styles from "./SectionNavigation.module.css";

const ICON_PATHS: Record<string, string> = {
  exemys: "M4 9h16v11H4zM8 9V5h8v4M8 14h.01M12 14h.01M16 14h.01M9 20v-3h6v3",
  charito: "M3 4h18v16H3zM7 9l3 3-3 3M13 15h4",
  generadores: "M13 2L4 14h7l-1 8 10-13h-7z",
  proxmox: "M4 3h16v7H4zM4 14h16v7H4zM8 6.5h.01M8 17.5h.01M12 6.5h5M12 17.5h5",
  reles: "M3 5h18v14H3zM7 12h3m4 0h3M10 12l4-4M10 12h.01M14 12h.01",
  analizadores: "M3 3v18h18M6 15l4-5 4 3 6-8",
  caudalimetros: "M12 2C10 6 5 10 5 14a7 7 0 0 0 14 0c0-4-5-8-7-12zM9 15a3 3 0 0 0 3 3",
  mantenimiento: "M14 5a5 5 0 0 0-6 6l-5 5a3 3 0 0 0 4 4l5-5a5 5 0 0 0 6-6l-3 3-3-3z",
  mensagelo: "M3 4h18v13H9l-6 4zM7 8h10M7 12h7",
  broker: "M10 9h4v6h-4zM3 3h4v4H3zM17 3h4v4h-4zM3 17h4v4H3zM17 17h4v4h-4zM7 5l3 4M17 5l-3 4M7 19l3-4M17 19l-3-4",
  email: "M3 5h18v14H3zM3 5l9 8 9-8",
};

export function SectionNavigation({ items, path, onNavigate }: {
  items: NavigationItem[];
  path: string;
  onNavigate: (href: string) => void;
}) {
  function moveFocus(event: KeyboardEvent<HTMLAnchorElement>, index: number) {
    if (event.ctrlKey || event.metaKey || event.altKey || !items.length) return;
    const next = event.key === "ArrowDown" ? (index + 1) % items.length
      : event.key === "ArrowUp" ? (index - 1 + items.length) % items.length
      : event.key === "Home" ? 0 : event.key === "End" ? items.length - 1 : null;
    if (next === null) return;
    event.preventDefault();
    event.currentTarget.closest("nav")?.querySelectorAll<HTMLAnchorElement>("a")[next]?.focus();
  }

  return (
    <nav className={styles.navigation} aria-label="Secciones de lechuza-server">
      {items.map((item, index) => {
        const section = item.href.split("/").filter(Boolean).at(-1) ?? "";
        return (
          <a key={item.href} href={`${item.href}/`} title={item.label} aria-label={item.label}
            aria-current={path.replace(/\/$/, "") === item.href ? "page" : undefined}
            onKeyDown={event => moveFocus(event, index)}
            onClick={event => {
              if (event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
              event.preventDefault();
              onNavigate(`${item.href}/`);
            }}>
            <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
              <path d={ICON_PATHS[section] ?? "M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h6v6h-6z"} />
            </svg>
            <span>{item.label}</span>
          </a>
        );
      })}
    </nav>
  );
}
