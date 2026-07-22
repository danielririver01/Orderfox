# Buyer Persona — Velzia (Orderfox + Copilot VZ)

> Persona única y concreta del cliente ideal de **Velzia**: el dueño de restaurante
> que usa **Orderfox** (gestión) y **Copilot VZ** (analista de negocios IA).
> Construida sobre features reales del producto (ver `docs/02-GUIDES/GUIDE-07_Copilot_VZ.md`).

---

## Persona — Diego Restrepo

> *"Yo no quiero aprender a leer gráficas. Quiero preguntarle a alguien y que me diga: ¿estoy perdiendo plata o no?"*

### Ficha técnica
| Campo | Valor |
|---|---|
| **Nombre** | Diego Restrepo |
| **Edad** | 41 años (nació en 1985) |
| **Ciudad** | Bogotá, Colombia (local principal en La Candelaria; segundo en Chía) |
| **Negocio** | "La Brasa de Diego" — parrilla + café, 2 locales |
| **Rol** | Dueño único (persona natural), 9 empleados en nómina |
| **Mesas / canal** | 14 mesas + delivery (Rappi) + mostrador |
| **Ingresos del negocio** | ~$45.000.000 COP/mes; utilidad aproximada 12–15% |
| **Sueldo que se paga** | ~$6.000.000 COP/mes |
| **Formación** | Técnico en gastronomía, no analítico; Excel básico "para llevar cuentas" |
| **Tecnología** | Samsung Galaxy A54 (Android), navega desde el celular; WhatsApp Business para clientes |
| **TPV actual** | Máquina de punto de venta básica (no integrada a la nube) |
| **Idioma** | Español (colombiano) |
| **Suscripción Velzia** | Plan Básico (100 créditos/mes) |

### Una semana real de Diego
- **Lunes:** abre, revisa inventario de carnes "a ojo", negocia con el distribuidor por WhatsApp.
- **Miércoles:** cierra la caja, sospecha que el mes va flojo pero no sabe por qué.
- **Viernes–Sábado:** el local lleno; el domingo, en cambio, entra la mitad de clientes y no entiende por qué.
- **Fin de mes:** la utilidad bajó respecto al mes anterior; culpables posibles: "subió la carne", "vinieron menos personas", "se botó comida". No lo sabe con certeza.
- **Cada tanto:** abre Velzia desde el celular y le escribe a Copilot VZ.

### Qué lo frustra (pain específico)
- El proveedor de carnes subió el precio y **no notó el golpe en el margen** hasta el cierre mensual.
- No sabe **qué plato le da pérdida** (los vende porque "la gente los pide" pero el costo lo come).
- Siente que "los domingos van mal" pero no tiene el dato; decide por instinto.
- Las herramientas de BI le parecen para "otros" (analistas), no para él.
- Ya paga una TPV y un proveedor de delivery; una herramienta más le suena a "otra mensualidad".

### Qué quiere (goals)
- Entender el negocio **en lenguaje natural**: *"¿qué plato me da pérdida y por qué?"*, *"¿subió el costo de pollo?"*.
- Que la IA **le avise sola** cuando hay un patrón raro (eventos automáticos), sin que él deba revisar un tablero.
- Comparar meses, ver el ticket promedio y la tendencia, sin tocar una hoja de cálculo.
- Recuperar margen sin trabajar más horas en la cocina.

### Cómo usa Velzia (journey con Copilot VZ)
1. **Onboarding (nivel 0→3):** crea su primer producto/categoría, registra una venta de prueba; el sistema le muestra sugerencias según la madurez de sus datos.
2. **Consulta rápida (GRATIS):** *"¿cuánto vendí ayer?"* → Copilot responde con SQL directo + gráfica, **sin consumir créditos**.
3. **Análisis profundo (1 crédito):** *"¿qué plato me da pérdida?"* → pasa a DeepSeek, le explica en tono colombiano cercano y le sugiere siguiente pregunta.
4. **Evento automático:** el `event_engine` detecta *"ventas bajas los domingos"* y le deja una tarjeta en el dashboard; Diego la toca → se abre la conversación ya precargada.
5. **Menú digital (Astro):** publica su carta online para vender sin mesero extra.
6. **Seguimiento (sin crédito):** en la misma conversación pregunta *"¿y el pollo?"* → no descuenta crédito.

### Objeciones y cómo Velzia las desactiva
- *"No soy técnico."* → Copilot habla español coloquial, no SQL; el disclaimer *"puede cometer errores"* lo protege.
- *"No tengo tiempo."* → las respuestas llegan en segundos, desde el celular; los eventos aparecen solos.
- *"Ya pago otra herramienta."* → Velzia no reemplaza la TPV: se monta encima para explicar el **por qué**, no para cobrar.
- *"La IA se equivoca."* → reglas estrictas: no inventa cifras, solo interpreta datos que Flask ya procesó.

### Mensaje que lo convence
> **"Tu restaurante, explicado en palabras simples. Hazle preguntas a Velzia y te dice qué hacer."**

### Dónde lo alcanzamos (canal / trigger)
- El momento "este mes no cuadra" (fin de mes).
- Recomendación boca a boca entre dueños (grupos de restauranteros).
- La demo del **menú digital** como anzuelo de entrada.
- El primer evento automático que le dice algo que él no sabía.

---

## Cliente ideal en una frase
> **Diego, 41, dueño práctico de 2 locales que quiere entender su negocio hablándole a una IA, no leyendo gráficas.**

## Principio rector (no violar)
> **"Copilot VZ no muestra datos. Descubre cosas que el dueño probablemente no habría visto por sí solo."**
> (coherente con la filosofía de producto de Velzia: insights silenciosos, no dashboards que exijan interpretación)
