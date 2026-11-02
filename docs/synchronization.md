# Sincronización bidireccional con MikroTik

## Endpoint

```http
POST /api/clientes-pppoe/sincronizar/
```

La ruta histórica `/api/clientes-pppoe/importar-desde-mikrotik/` se conserva por compatibilidad y ejecuta la misma operación. Para operaciones nuevas, preferir `/api/routers/{id}/sincronizar/`.

## Qué sincroniza

La operación compara los siguientes recursos de RouterOS con sus registros de Django:

- `/ppp/profile` con `PlanVelocidad`.
- `/ppp/secret` con `ClientePPPoE`.

## Direcciones de la sincronización

### MikroTik hacia Django

- Crea o actualiza planes locales encontrados en `/ppp/profile`.
- Crea o actualiza clientes locales encontrados en `/ppp/secret`.
- Convierte `rate-limit` de RouterOS a velocidades de subida y bajada en Mbps.
- Asocia secretos con un plan local según el nombre del profile.

### Django hacia MikroTik

- Crea los profiles locales que no existan en el router.
- Actualiza el `rate-limit` de los profiles existentes.
- Crea los secretos PPP locales que no existan en el router.
- Actualiza la contraseña, el profile y el servicio `pppoe` de secretos existentes.

## Reglas importantes

- La sincronización utiliza el primer router registrado en Django.
- Los registros no presentes en ambos sistemas se crean; esta operación no elimina automáticamente registros existentes.
- Los nombres de usuarios se normalizan a minúsculas.
- El usuario Django y el secreto RouterOS deben usar el mismo nombre para considerarse el mismo registro.
- Los cambios se envían dentro de una transacción local. Un error de RouterOS puede detener la operación, aunque algunas llamadas ya realizadas al router no puedan revertirse automáticamente.
- El modo simulación impide ejecutar la sincronización real.

## Formato de respuesta

```json
{
  "message": "Sincronización bi-direccional finalizada",
  "details": {
    "planes_creados": 1,
    "planes_actualizados": 1,
    "clientes_importados": 1,
    "clientes_actualizados": 1,
    "secretos_creados": 1,
    "secretos_actualizados": 1
  }
}
```

## Formato de velocidad

RouterOS devuelve `rate-limit` con el formato `subida/bajada`, por ejemplo:

```text
10M/20M
10240k/20480k
```

En Django se almacenan por separado como Mbps enteros.

## Identificadores de RouterOS

La biblioteca API puede exponer el identificador interno de un elemento como `.id`, `id` o `*id`. El servicio normaliza estos formatos antes de ejecutar las operaciones `set` y `remove`.
