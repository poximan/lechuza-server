import { Button } from "@servicoop/frontend-foundation";
import { useEffect } from "react";

import styles from "./RelayDisturbanceHelpModal.module.css";

export function RelayDisturbanceHelpModal({ onClose }: { onClose: () => void }) {
  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [onClose]);

  return (
    <div
      className={styles.backdrop}
      onPointerDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <section
        aria-labelledby="relay-disturbance-help-title"
        aria-modal="true"
        className={styles.modal}
        role="dialog"
      >
        <header className={styles.header}>
          <div>
            <h2 id="relay-disturbance-help-title">Lectura de perturbaciones MiCOM</h2>
            <p>Secuencia definida por el manual P12x/EN CT/Da6.</p>
          </div>
          <Button autoFocus onClick={onClose} variant="ghost">Cerrar</Button>
        </header>

        <p>
          Cada operación Modbus usa función 03 y se encola en el canal. Solo se
          despacha una petición física por vez y la siguiente espera su respuesta.
        </p>

        <ol className={styles.steps}>
          <li>
            <strong>Inventario — <code>0x3D00</code>, 36 palabras.</strong>
            <span>
              La palabra 1 informa cuántas perturbaciones conserva la SRAM. Luego
              hay cinco grupos de 7 palabras: número de registro; dos palabras de
              fecha de finalización en segundos; dos de milisegundos; origen del
              arranque; y reconocimiento. Una respuesta válida con cantidad cero
              confirma que el relé no tiene capturas disponibles actualmente.
              Algunos equipos expresan el mismo estado con la excepción MiCOM
              <code> 0x0F</code>, que también se interpreta como inventario vacío.
            </span>
          </li>
          <li>
            <strong>Selección — páginas <code>0x38</code> a <code>0x3C</code>, 11 palabras.</strong>
            <span>
              Cada página selecciona uno de los registros 1 a 5. El nibble
              <code> x </code> selecciona bloques sucesivos de hasta 6250 muestras;
              el último dígito selecciona IA (<code>0</code>), IB (<code>1</code>),
              IC (<code>2</code>) o IE (<code>3</code>). Por ejemplo,
              <code> 0x3800 </code> pide el primer bloque de IA del registro 1 y
              <code> 0x3912 </code> el segundo bloque de IC del registro 2.
            </span>
            <span>
              Las palabras 1–3 de la respuesta indican muestras totales, preevento
              y postevento; las 4–9 contienen las relaciones de TC primarias,
              secundarias e internas de fase y tierra; la 10 indica la última página
              de datos y la 11 cuántas palabras de esa página son válidas. Las
              palabras opcionales 12–13 no se solicitan.
            </span>
          </li>
          <li>
            <strong>Muestras — <code>0x0900</code> a <code>0x21F9</code>.</strong>
            <span>
              Las 25 páginas contienen hasta 250 palabras de 16 bits del canal ya
              seleccionado. Como el protocolo admite entre 1 y 125 palabras por
              petición, cada página completa se divide en dos lecturas de 125. La
              última lectura usa exactamente la cantidad restante informada por la
              selección y nunca consulta palabras fuera del registro almacenado.
            </span>
          </li>
          <li>
            <strong>Índice — <code>0x2200</code>, 7 palabras obligatorias.</strong>
            <span>
              Sus palabras son: número de registro; cuatro palabras de fecha de
              finalización; condición de arranque; y frecuencia al comenzar el
              post tiempo. El número, la fecha y el origen deben coincidir con el
              inventario antes de aceptar la captura. Las palabras opcionales 8–9
              no se solicitan.
            </span>
          </li>
        </ol>

        <p>
          El procedimiento se repite para IA, IB, IC e IE. Las muestras son palabras
          de 16 bits con signo y se convierten a amperes primarios usando la relación
          de TC del encabezado y el factor √2. Las fechas se guardan en UTC y se
          presentan en hora local únicamente en esta pantalla.
        </p>

        <p className={styles.note}>
          El relé conserva como máximo 15 segundos distribuidos entre uno y cinco
          registros, según su configuración. Cuando se agota la memoria, una captura
          nueva sobrescribe la más antigua. Una captura descargada no se borra cuando
          deja de aparecer en el inventario; el mismo número de registro se reemplaza
          únicamente cuando el relé lo reutiliza para un evento nuevo.
        </p>
      </section>
    </div>
  );
}
