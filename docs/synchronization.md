# Sincronización bidireccional con MikroTik

## Endpoint

```http
POST /api/routers/{id}/sincronizar/
```

Se retiraron las rutas históricas basadas en `/api/clientes-pppoe/`, porque ambas resolvían al primer router y podían sincronizar un equipo distinto al esperado. El flujo oficial usa `/api/routers/{id}/sincronizar/`, que identifica el router por su ID.

## Qué sincroniza

La operación compara los siguientes recursos de RouterOS con sus registros de Django:

- `/ppp/profile` con `PlanVelocidad`.
- `/ppp/secret` con `ClientePPPoE`.

## Direcciones de la sincronización

### MikroTik hacia Django

- Crea o actualiza planes locales encontrados en `/ppp/profile`, salvo los
  perfiles de sistema (`default`, `default-encryption`), que no son planes
  del ISP y no se importan.
- Crea o actualiza clientes locales encontrados en `/ppp/secret`.
- Convierte `rate-limit` de RouterOS a velocidades de subida y bajada en Mbps.
- Asocia secretos con un plan local según el nombre del profile. Si el
  profile del secreto no existe como plan (ni en Django ni en
  `/ppp/profile` del router), el secreto **no se importa y no se inventa
  ningún plan**: queda listado en `secretos_saltados_sin_plan` dentro de
  `details`, con un aviso en `advertencias`.
- Si el secreto no tiene contraseña en el router, **no se importa**: antes
  se creaba el cliente con la contraseña débil `123456`. Queda listado en
  `secretos_saltados_sin_password` y en `advertencias`; hay que ponerle una
  contraseña en WinBox y volver a sincronizar.
- Guarda el `local-address` y el `remote-address` del profile en el plan (`direccion_local` y `pool_remoto`) cuando el router los tiene definidos.

La sincronización solo cubre profiles y secrets: no sincroniza colas simples, leases DHCP ni reservas ARP.

### Django hacia MikroTik

- Crea los profiles locales que no existan en el router.
- Actualiza el `rate-limit` de los profiles existentes.
- Si el plan tiene `direccion_local` o `pool_remoto`, también crea o
  actualiza el profile con ese `local-address` y `remote-address`. Si el plan
  no los tiene, no toca esos campos del perfil que ya existe en el router.
- Si el plan tiene `cola_padre`, el profile se crea o actualiza con ese
  `parent-queue`; si no tiene, no se toca ese campo del perfil existente.
- Crea los secretos PPP locales que no existan en el router.
- Actualiza la contraseña, el profile y el servicio `pppoe` de secretos existentes.

## Reglas importantes

- La sincronización utiliza el router indicado en la URL `/api/routers/{id}/sincronizar/`.
- Los registros no presentes en ambos sistemas se crean; esta operación no elimina automáticamente registros existentes.
- Los nombres de usuarios se normalizan a minúsculas.
- El usuario Django y el secreto RouterOS deben usar el mismo nombre para considerarse el mismo registro.
- Los cambios se envían dentro de una transacción local. Un error de RouterOS puede detener la operación, aunque algunas llamadas ya realizadas al router no puedan revertirse automáticamente.
- El modo simulación impide ejecutar la sincronización real. El modo simulación está fijado a `false` en `core/settings.py` (los servicios hablan con el router real), así que en la práctica este caso no se da salvo que se cambie ese ajuste en el código.

## Formato de respuesta

```json
{
  "status": "success",
  "message": "Sincronización bi-direccional finalizada",
  "details": {
    "planes_creados": 1,
    "planes_actualizados": 1,
    "clientes_importados": 1,
    "clientes_actualizados": 1,
    "secretos_creados": 1,
    "secretos_actualizados": 1,
    "secretos_saltados_sin_password": ["usuario.sin.clave"],
    "secretos_saltados_sin_plan": ["usuario.raro (perfil 'PlanX' sin plan)"],
    "perfiles_sistema_saltados": ["default"],
    "advertencias": ["Secretos sin contraseña en el router, no importados: ..."]
  }
}
```

Si falla, devuelve `{"status": "error", "message": "..."}` con código 502.

## Formato de velocidad

RouterOS devuelve `rate-limit` con el formato `subida/bajada`, por ejemplo:

```text
10M/20M
10240k/20480k
```

En Django se almacenan por separado como Mbps enteros.

## Identificadores de RouterOS

La biblioteca API puede exponer el identificador interno de un elemento como `.id`, `id` o `*id`. El servicio normaliza estos formatos antes de ejecutar las operaciones `set` y `remove`.
