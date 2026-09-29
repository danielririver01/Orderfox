# 09 — Seguridad: qué se revisó y qué no (AS-IS)

**Commit de referencia:** `cd96aa763c086dea93e4aede46191b9add9067fa` · **Fecha:** 2026-09-29

---

## 1. Declaración de alcance

> **Este trabajo NO es una auditoría de seguridad.**
>
> Es un diagnóstico AS-IS: describe cómo está construido el sistema y verifica
> su comportamiento. Los hallazgos de seguridad que contiene aparecieron **como
> subproducto** de esa revisión, no de una búsqueda sistemática de
> vulnerabilidades.
>
> Quien lea los documentos 3.1 y 2.6 y concluya «el sistema está auditado»
> estaría sacando una conclusión que estos documentos no sostienen.

Este documento existe para que esa frontera quede escrita, no supuesta.

---

## 2. Lo que sí se comprobó

### 2.1 Aislamiento entre inquilinos — `[EJECUTADO]` ✅

La prueba más importante de un SaaS multi-inquilino: ¿puede el restaurante A
ver o tocar los datos del restaurante B?

**Montaje:** dos restaurantes con datos marcados — `SECRETO-A` / `SECRETO-B`,
pedidos con notas `DATO CONFIDENCIAL DE A` / `DE B`. Sesión del dueño A; se
intentó alcanzar los identificadores de B.

| Intento del dueño A sobre datos de B | Resultado | ¿Fuga? |
|---|---|---|
| `GET /orders/2` | **404** | no |
| `GET /api/orders/2` | **404** | no |
| `PATCH /orders/2/status` | **400** (CSRF) | no |
| `GET /products/2/edit` | **404** | no |
| `GET /api/products/2` | **404** | no |
| `DELETE /api/products/2` | **404** | no |
| `GET /api/categories/2` | **404** | no |
| `GET /api/tables/2` | **405** | no |
| `GET /dashboard/api/stats?restaurant_id=2` | **200** — pero devuelve los datos **de A**: el parámetro se ignora y se usa el restaurante de la sesión | no |
| Empleado de A entrando al portal de B con su PIN | **401** | no |
| `GET /api/public/menu/sazon-valle` (menú público de B) | **200** — correcto, es público por diseño | n/a |

**Control:** los mismos endpoints sobre los datos propios de A devuelven **200**,
así que los 404 son aislamiento real y no rutas rotas.

**Veredicto:** el aislamiento por `restaurant_id` **funciona en los endpoints
probados**. No se detectó ninguna fuga entre inquilinos.

> ⚠️ Se probaron **11 endpoints** de los ~200 que existen. Es una muestra, no
> una demostración exhaustiva.

### 2.2 Autorización por roles — `[EJECUTADO]` ✅

Verificado en [2.6 · Verificación en ejecución](08-verificacion-en-ejecucion.md):
el cajero recibe **403** al cerrar caja, el mesero no alcanza la pantalla, y
ninguno de los dos entra al panel del dueño. La cadena
`require_auth → require_active → require_role` se ejecuta de verdad.

### 2.3 Cabeceras de seguridad — `[EJECUTADO]` ✅

Siete cabeceras verificadas en respuesta real: `X-Frame-Options: DENY`,
`X-Content-Type-Options`, `Referrer-Policy`, `Permissions-Policy`,
`Strict-Transport-Security`, `Cache-Control` y CSP. Detalle en
[2.2 · Arquitectura actual §9](02-arquitectura-actual.md#9-cabeceras-de-seguridad).

**Salvedades ya registradas:** la CSP incluye `'unsafe-inline'` y `'unsafe-eval'`;
`SESSION_COOKIE_SECURE` está en `False` sin forma de activarlo por entorno
([R-07](06-riesgos-y-deuda-tecnica.md#r-07)).

### 2.4 Anti-abuso del menú público — `[EJECUTADO]` ⚠️

Honeypot (**403**) y límite de 3 pedidos/minuto (**429**) funcionan. La tercera
capa, el tiempo mínimo de 3 segundos, **está inerte**
([R-17](08-verificacion-en-ejecucion.md#r-17)).

### 2.5 Análisis estático con bandit — `[EJECUTADO]`

`bandit` está en `requirements-dev.txt` pero **el CI nunca lo ejecuta**. Se
ejecutó aquí por primera vez:

```
líneas analizadas: 17.298
ALTA: 1 · MEDIA: 0 · BAJA: 7
```

**El único hallazgo ALTO es un falso positivo.** Es `app/utils/cover_bank.py:87`:

```python
def cuisine_hash(cuisine_type):
    """Digest determinista del cuisine_type (utilidad para tests / debugging)."""
    return hashlib.sha1(cuisine_type.encode('utf-8')).hexdigest()[:8]
```

SHA-1 usado como digest determinista para depuración, no como control de
seguridad. No hay nada que arreglar salvo, si se quiere silenciar la alerta,
pasar `usedforsecurity=False`.

**Resultado honesto: bandit no encontró ningún problema real.** Es una señal
buena, pero bandit solo detecta patrones conocidos; no prueba lógica.

### 2.6 Vulnerabilidades en dependencias — `[EJECUTADO]` ❌ ver R-23

Primera ejecución de `pip-audit` sobre el entorno instalado. **Encontró CVEs**,
detalladas en [R-23](#r-23).

---

## 3. Lo que NO se revisó

Esta es la parte importante del documento.

| Área | Estado | Por qué |
|---|---|---|
| **Autenticación** (Clerk, alta, login, `/api/sync-clerk`) | ❌ **sin probar** | Requiere credenciales reales. La sesión del dueño se **simuló** con una cookie firmada — ver [2.6 §9](08-verificacion-en-ejecucion.md) |
| ~~JWT Bearer~~ | ✅ **probado** | Ver §2.8: funciona, resiste firma manipulada y `alg=none`. Falta la emisión real vía Clerk |
| **Inyección SQL** | ❌ sin probar | No se hicieron pruebas de inyección. El ORM parametriza por defecto, pero eso es una expectativa, no una comprobación |
| **XSS** (reflejado, almacenado, DOM) | ❌ sin probar | La CSP con `unsafe-inline` reduce la mitigación disponible |
| ~~Falsificación de firma de webhooks~~ | ✅ **probado** | Ver [R-24](#r-24): la firma de Mercado Pago **no sigue la especificación oficial**. El webhook de Clerk (Svix) sigue sin probar |
| **Subida de archivos** | ❌ sin probar | Cloudinary, `image_handler`, límite de 16 MB: sin pruebas de tipo, tamaño ni contenido malicioso |
| **Inyección de prompts en el Copilot** | ❌ sin probar | Hay tres capas documentadas en el código; **ninguna se puso a prueba** |
| **Escaneo de secretos** | ❌ **no ejecutado** | `.gitleaks.toml` existe, pero gitleaks no está instalado en el entorno de revisión |
| **Suite de seguridad del propio repo** (ZAP, Trivy) | ❌ no ejecutada | Orquestada con PowerShell: solo Windows ([R-13](06-riesgos-y-deuda-tecnica.md#r-13)) |
| **Fijación / robo de sesión, manipulación de cookies** | ❌ sin probar | Se firmó una cookie válida conociendo la `SECRET_KEY` de prueba, lo cual no prueba nada sobre producción |
| **Aislamiento en los ~190 endpoints restantes** | ❌ sin probar | Se probaron 11 |
| **Abuso de lógica de negocio** más allá de los límites de tasa | ❌ sin probar | P. ej. manipulación de precios, reservas masivas, agotamiento de créditos de IA |
| **Infraestructura** (nginx, systemd, TLS, servidor) | ❌ fuera de alcance | No hay acceso al servidor |

---

### 2.7 Verificación de firma de webhooks — `[EJECUTADO]` ❌ ver R-24

Se pueden probar **sin ninguna credencial**: ambos webhooks validan contra un
secreto compartido que uno mismo puede fijar. El resultado es
[R-24](#r-24), el hallazgo más grave de todo el diagnóstico.

### 2.8 Autenticación por JWT — `[EJECUTADO]` ✅

También verificable sin credenciales: el token lo firma la propia aplicación con
`JWT_SECRET_KEY`. Se emitió uno con `create_access_token` y se atacó la vía:

| Prueba | Resultado |
|---|---|
| Token válido → `GET /api/products` | **200** ✅ la vía JWT funciona |
| Firma manipulada | **401** ✅ |
| **Ataque `alg=none`** (confusión de algoritmo) | **401** ✅ *«The specified alg value is not allowed»* |
| Sin token | **302** ⚠️ redirige al login en vez de devolver 401 |

**Veredicto:** la autenticación por JWT resiste lo básico, incluido el ataque
clásico de `alg=none`. El **302 sin token** no es un agujero, pero para un
cliente de API es un mal comportamiento: debería ser `401`.

`[EJECUTADO]` Observado de paso: con una `JWT_SECRET_KEY` corta, PyJWT avisa
`InsecureKeyLengthWarning: The HMAC key is 6 bytes long, below the minimum
recommended 32 bytes`. En la prueba la clave la puse yo; **queda por confirmar
la longitud de la clave real en producción**.

---

## 4. Hallazgos nuevos

<a id="r-24"></a>
### 🔴 R-24 — La verificación de firma de Mercado Pago no sigue la especificación oficial: **rechaza todos los webhooks reales**

**Estado:** `[EJECUTADO]` — reproducido contra ambos endpoints.

#### La especificación oficial

La documentación de Mercado Pago define el manifiesto así:

```
id:{data.id};request-id:{x-request-id};ts:{ts};
```

y sobre él calcula `HMAC-SHA256(clave_secreta, manifiesto)` en hexadecimal, que
compara contra `v1` del header `x-signature`.

#### Lo que implementa Orderfox

`app/utils/mp_webhook.py:44-50`:

```python
message = f"{data_id}.{ts}.{secret}"
expected = hmac.new(secret.encode('utf-8'), message.encode('utf-8'),
                    hashlib.sha256).hexdigest()
return hmac.compare_digest(expected, v1)
```

Tres diferencias con la especificación:

1. El separador y el formato no coinciden (`.` en vez de la plantilla `id:…;request-id:…;ts:…;`).
2. **No usa `x-request-id`.** `[EJECUTADO]` `grep -rn "x-request-id" app/` →
   **cero coincidencias en todo el repositorio**: el dato que MP exige para
   construir el manifiesto no se lee nunca.
3. Mete el secreto *dentro* del mensaje firmado, además de usarlo como clave
   del HMAC.

#### Prueba en ejecución

Con `MP_WEBHOOK_SECRET` configurado, enviando el cuerpo y las cabeceras que
envía Mercado Pago:

```
Manifiesto oficial : id:132646402927;request-id:5e278faa-…;ts:1790653594;
Mensaje de Orderfox: 132646402927.1790653594.<secreto>

POST /api/v1/webhooks/mercadopago
  firma REAL de Mercado Pago (manifiesto oficial) ->  401  invalid_signature   ❌
  firma con el formato propio de Orderfox         ->  500  server_config
        (la firma SE ACEPTA; el 500 es por falta de MP_ACCESS_TOKEN)
  firma inventada (control)                       ->  401  invalid_signature   ✅

POST /webhook  (legacy)
  firma REAL de Mercado Pago                      ->  401  invalid_signature   ❌
```

**El verificador funciona; lo que no coincide es el esquema.** Una notificación
legítima de Mercado Pago se rechaza igual que una falsificada.

#### Impacto

Ambos caminos del webhook son **fail-closed**, así que no hay riesgo de aceptar
un pago falso. El problema es el contrario:

| Configuración | Comportamiento con un webhook real de MP |
|---|---|
| `MP_WEBHOOK_SECRET` **configurado** | **401** — la firma nunca cuadra |
| `MP_WEBHOOK_SECRET` **sin configurar** | **503** `webhook_not_configured` |

**En las dos, el pago no se confirma nunca por webhook.** La única vía que
acredita una suscripción es `/payment-callback`, la redirección del navegador al
volver del checkout — que depende de que el cliente **regrese al sitio**. Si
cierra el navegador tras pagar, queda pagado y sin acceso.

`[INFERIDO]` Eso encajaría con incidencias del tipo «pagué y no se me activó».
**Conviene contrastarlo con los casos de soporte reales antes de dar por cierta
la consecuencia.**

#### Límite de esta evidencia

No se contrastó contra tráfico real de Mercado Pago. La base son: (a) la
especificación oficial y los SDK de MP, corroborados por varias fuentes
independientes, y (b) la comprobación en ejecución de que una firma construida
según esa especificación se rechaza. **La prueba definitiva es enviar una
notificación de prueba desde el panel de Mercado Pago.**

#### Criterio de cierre

- [ ] Reescribir `verify_mp_signature` con el manifiesto oficial
- [ ] Leer y propagar `x-request-id` hasta la verificación
- [ ] Tomar `data.id` del *query param* además del cuerpo (MP lo envía en ambos)
- [ ] Prueba con firmas calculadas **fuera** de la implementación, para no validarla contra sí misma
- [ ] Notificación de prueba desde el panel de MP contra un entorno de pruebas
- [ ] Revisar si hay pagos históricos cobrados y no acreditados

---

<a id="r-23"></a>
### 🟠 R-23 — Dependencias con CVE conocidas, y el CI no ejecuta las herramientas que ya están instaladas

**Estado:** `[EJECUTADO]` — `pip-audit` sobre el entorno real.

**Paquetes fijados en `requirements.txt` con vulnerabilidades conocidas:**

| Paquete | Versión fijada | CVE | Corregido en | Lo arrastra |
|---|---|---|---|---|
| `cryptography` | **48.0.1** | PYSEC-2026-3552, -3553, -3554 | 49.0.0 / 50.0.0 | Authlib |
| `idna` | **3.11** | PYSEC-2026-215 | 3.15 | requests, httpx, email-validator |
| `pyasn1` | **0.6.3** | PYSEC-2026-3455, -3456, -3457 | 0.6.4 | — |

`cryptography` es el más relevante: lo usa **Authlib**, que está en el camino de
autenticación.

**También vulnerables, pero transitivas o solo de desarrollo:** `setuptools`
66.1.1 (3 CVE), `filelock` 3.16.1, `nltk` 3.10.3, `pytest` 8.3.4.

**Lo que agrava el hallazgo:** `bandit==1.8.3` y `safety==3.3.1` están en
`requirements-dev.txt`, pero **`.github/workflows/ci.yml` no los menciona ni una
vez**. Las herramientas están compradas y sin estrenar. Es el mismo patrón que
[R-10](06-riesgos-y-deuda-tecnica.md#r-10) (flake8 con `--exit-zero`): la
comprobación existe pero no puede fallar el build.

**Criterio de cierre:**

- [ ] Subir `cryptography`, `idna` y `pyasn1` a versiones sin CVE
- [ ] Añadir `pip-audit` (o `safety`) al CI, **sin** `--exit-zero`
- [ ] Añadir `bandit`, aunque sea informativo al principio
- [ ] Decidir qué hacer con la suite de seguridad solo-Windows: portarla o retirarla

---

## 5. Qué haría falta para poder decir «está auditado»

Ninguna de estas cosas se hizo. Se listan para dimensionar la distancia.

1. **Pruebas de autenticación** con credenciales reales de Clerk, incluyendo el
   flujo de JWT.
2. **Pruebas de autorización exhaustivas**: recorrer los ~200 endpoints con
   identidades de distinto inquilino y distinto rol, no una muestra de 11.
3. **Pruebas de inyección**: SQL, XSS, plantillas y prompts al LLM.
4. **Pruebas de los webhooks**: intentar falsificar firmas de Mercado Pago y de
   Clerk, y comprobar la idempotencia ante reenvíos.
5. **Escaneo de secretos** sobre todo el historial de Git, no solo el árbol actual.
6. **Escaneo de la imagen de contenedor** (Trivy) y del servidor.
7. **Revisión de la configuración de producción**: TLS, nginx, permisos,
   variables de entorno, rotación de `SECRET_KEY`.
8. **Modelo de amenazas** del negocio: qué se protege, contra quién, y qué
   pérdida es aceptable.

Los puntos 1 a 4 son ejecutables en este mismo entorno **en cuanto haya
credenciales de prueba**. Los puntos 5 a 7 requieren acceso a la
infraestructura. El punto 8 requiere al propietario.

---

## 6. Resumen en una línea

**Lo que funciona:** el aislamiento entre restaurantes, la separación de roles,
las cabeceras de seguridad, la autenticación por JWT (incluido `alg=none`) y
bandit limpio.

**Lo que está roto:** la verificación de firma de Mercado Pago rechaza los
webhooks legítimos ([R-24](#r-24)), y hay dependencias con CVE conocidas
([R-23](#r-23)).

**Lo que sigue sin saberse:** si la autenticación con Clerk es sólida, si hay
inyecciones (SQL, XSS, prompts), si el webhook de Clerk se puede falsificar, y
si hay secretos en el historial de Git. **Nada de eso se probó.**

> 🔎 **Una lección de este documento.** R-24 y la verificación del JWT salieron
> de una pregunta del propietario: *«¿esto fue auditoría con seguridad
> incluida?»*. Ninguna de las dos necesitaba credenciales —ambas se validan
> contra secretos que uno mismo fija— y sin embargo no estaban hechas. **El
> diagnóstico había confundido «requiere un tercero» con «requiere sus
> credenciales».**
