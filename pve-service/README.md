# pve-service

El recolector conserva el intervalo `PVE_POLL_INTERVAL_SECONDS`; las consultas de
disco forman parte de ese mismo ciclo, no de cada refresco del navegador. Todos
los endpoints adicionales se consultan mediante GET con el token/TLS existentes.

## Discos virtuales y ocupación interna

`GET /api/pve/state` agrega a cada elemento de `vms`:

- `virtual_disks`: discos de datos conectados (`scsi`, `virtio`, `sata`, `ide`), con
  identificador, volumen de Proxmox y `total_bytes` configurados. No incluye CD-ROM,
  discos desconectados, EFI ni TPM. Fuente: `/nodes/{node}/qemu/{vmid}/config`.
- `filesystems`: volúmenes montados del sistema invitado, con nombre, punto de
  montaje, tipo, dispositivos informados por el agente, `used_bytes`,
  `total_bytes`, `available_bytes` y `used_pct`. Fuente:
  `/nodes/{node}/qemu/{vmid}/agent/get-fsinfo`, respuesta `data.result`.
- `disk_usage_status` y `disk_usage_error`: estado/motivo de indisponibilidad.
  Estados: `ok`, `partial`, `config_unavailable`, `stopped`, `agent_disabled`,
  `permission_denied`, `agent_unavailable`.

La ocupación es la del sistema de archivos dentro del vhost; no es el tamaño del
archivo qcow2 ni la reserva del almacenamiento físico. Un volumen puede abarcar
múltiples discos y un disco puede tener varias particiones. Por ello se muestran
ambos inventarios sin emparejarlos por posición ni sumar volúmenes. Se conserva la
identificación de dispositivos suministrada por QEMU. Las capacidades usan bytes
y potencias de 1024; los porcentajes tienen como máximo dos decimales.

Un cero medido se conserva. La falta de medición queda como `null`/lista vacía con
su motivo y nunca como 0 %. El `disk=0` de `status/current` de QEMU no se interpreta
como ocupación interna. El campo legado `disk_pct` queda en `null`; su ausencia no
interrumpe el histórico de CPU/memoria. Los fallos del agente o del almacenamiento
general tampoco descartan esas métricas ni declaran al hipervisor desconectado.

Requisitos para cada VM: habilitar QEMU Guest Agent en sus opciones de Proxmox,
instalarlo e iniciarlo dentro del invitado y permitir su consulta al usuario/token.
En Proxmox 8, `get-fsinfo` exige `VM.Monitor`; en Proxmox 9 se separó como
`VM.GuestAgent.Audit`. Con separación de privilegios del token, el permiso efectivo
debe estar autorizado tanto al usuario como al token, en `/vms/{vmid}` o un ámbito
superior aplicable. Este servicio no modifica permisos, configuración ni invitados.

## Almacenamiento general de Proxmox

La propiedad de primer nivel `host_storage` contiene `rootfs`, `storages` y
`errors`. Se obtiene del `rootfs` de `/nodes/{node}/status` y de
`/nodes/{node}/storage`. Cada almacenamiento conserva identificador, tipo,
actividad, si es compartido y sus bytes/porcentaje; se omiten los deshabilitados.
La interfaz lo muestra fuera de las tarjetas de vhost.

Estos son sistemas de archivos/pools/datastores, no necesariamente discos físicos
independientes: `local` puede coincidir con `/` y un datastore puede ser remoto.
No se suman sus capacidades ni se atribuye ese uso a una VM. Los errores parciales
se informan por separado.

Referencias: [QEMU Guest Agent](https://qemu-project.gitlab.io/qemu/interop/qemu-ga-ref.html#object-guestfilesysteminfo),
[privilegios del agente en Proxmox](https://lists.proxmox.com/pipermail/pve-devel/2025-July/073221.html),
[visor de la API Proxmox](https://pve.proxmox.com/pve-docs/api-viewer/).
