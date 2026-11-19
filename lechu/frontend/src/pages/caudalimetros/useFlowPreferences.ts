import { useCallback, useEffect, useRef, useState } from "react";
import { DEFAULT_FLOW_PREFERENCES, readFlowPreferences, writeFlowPreferences } from "./FlowPreferences";
import type { FlowPreferences } from "./FlowPreferences";

function initialPreferences(): { value: FlowPreferences; error: string | null } {
  try {
    return { value: readFlowPreferences(), error: null };
  } catch {
    return { value: { ...DEFAULT_FLOW_PREFERENCES }, error: "No se pudieron recuperar las preferencias guardadas. Se muestran los valores iniciales." };
  }
}

export function useFlowPreferences() {
  const [initial] = useState(initialPreferences);
  const [preferences, setPreferences] = useState(initial.value);
  const [preferenceError, setPreferenceError] = useState(initial.error);
  const latest = useRef(preferences);
  const saved = useRef(preferences);

  const persist = useCallback((reportError = true) => {
    if (latest.current === saved.current) return;
    try {
      writeFlowPreferences(latest.current);
      saved.current = latest.current;
      if (reportError) setPreferenceError(null);
    } catch {
      if (reportError) setPreferenceError("El navegador no permitió guardar las preferencias. Los cambios se conservan solo en esta vista.");
    }
  }, []);

  useEffect(() => {
    latest.current = preferences;
    // Agrupar las escrituras durante el arrastre de la ventana.
    const timer = window.setTimeout(() => persist(), 200);
    return () => window.clearTimeout(timer);
  }, [preferences, persist]);

  useEffect(() => {
    const flush = () => persist();
    window.addEventListener("pagehide", flush);
    return () => {
      window.removeEventListener("pagehide", flush);
      persist(false);
    };
  }, [persist]);

  const updatePreferences = useCallback((changes: Partial<FlowPreferences>) => {
    setPreferences(previous => Object.entries(changes).every(([key, value]) => Object.is(previous[key as keyof FlowPreferences], value))
      ? previous : { ...previous, ...changes });
  }, []);

  return { preferences, updatePreferences, preferenceError };
}
