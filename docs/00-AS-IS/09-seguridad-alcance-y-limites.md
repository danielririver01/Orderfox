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
| **JWT Bearer** (API móvil y Scanner IA) | ❌ **sin probar** | Ninguna prueba usó esa vía; todas fueron por cookie |
| **Inyección SQL** | ❌ sin probar | No se hicieron pruebas de inyección. El ORM parametriza por defecto, pero eso es una expectativa, no una comprobación |
| **XSS** (reflejado, almacenado, DOM) | ❌ sin probar | La CSP con `unsafe-inline` reduce la mitigación disponible |
| **Falsificación de firma de webhooks** | ❌ sin probar | El código verifica HMAC con `compare_digest` (`app/utils/mp_webhook.py:34-50`), pero **no se intentó falsificar ninguna firma** |
| **Subida de archivos** | ❌ sin probar | Cloudinary, `image_handler`, límite de 16 MB: sin pruebas de tipo, tamaño ni contenido malicioso |
| **Inyección de prompts en el Copilot** | ❌ sin probar | Hay tres capas documentadas en el código; **ninguna se puso a prueba** |
| **Escaneo de secretos** | ❌ **no ejecutado** | `.gitleaks.toml` existe, pero gitleaks no está instalado en el entorno de revisión |
| **Suite de seguridad del propio repo** (ZAP, Trivy) | ❌ no ejecutada | Orquestada con PowerShell: solo Windows ([R-13](06-riesgos-y-deuda-tecnica.md#r-13)) |
| **Fijación / robo de sesión, manipulación de cookies** | ❌ sin probar | Se firmó una cookie válida conociendo la `SECRET_KEY` de prueba, lo cual no prueba nada sobre producción |
| **Aislamiento en los ~190 endpoints restantes** | ❌ sin probar | Se probaron 11 |
| **Abuso de lógica de negocio** más allá de los límites de tasa | ❌ sin probar | P. ej. manipulación de precios, reservas masivas, agotamiento de créditos de IA |
| **Infraestructura** (nginx, systemd, TLS, servidor) | ❌ fuera de alcance | No hay acceso al servidor |

---

## 4. Hallazgo nuevo

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

**Lo que se sabe:** el aislamiento entre restaurantes y la separación de roles
funcionan en lo probado; las cabeceras están bien puestas; bandit está limpio.

**Lo que no se sabe:** si la autenticación es sólida, si hay inyecciones, si los
webhooks se pueden falsificar, y si hay secretos en el historial. **Nada de eso
se probó.**
