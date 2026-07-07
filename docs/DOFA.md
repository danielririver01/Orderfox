# Análisis DOFA — Orderfox / Velzia

**Fecha:** Julio 2026
**Producto:** Plataforma SaaS de gestión de pedidos para restaurantes colombianos
**Versión:** 1.3.0

---

## Fortalezas (Internas, Positivas)

1. **Producto completo y funcional** — La plataforma cubre todo lo que un restaurante necesita: menú digital, pedidos por código QR, panel de control para el dueño, notificaciones y pagos en línea. No es un prototipo, funciona en producción.

2. **Diferenciador con Inteligencia Artificial** — Incluye un escáner de facturas con IA que permite a los restaurantes llevar el control de sus gastos automáticamente. Ningún competidor en Colombia ofrece esto.

3. **Tecnología moderna y preparada para crecer** — Construida con herramientas actuales (Flask, SQLAlchemy, Tailwind CSS, Docker) que facilitan agregar nuevas funcionalidades y escalar.

4. **Protección contra bots y spam** — El sistema detecta automáticamente cuando un bot intenta hacer pedidos falsos y lo bloquea. Los clientes reales nunca tienen problemas.

5. **Pensado para Colombia** — Integración con Mercado Pago (la pasarela de pagos más usada en Colombia), precios en pesos colombianos, interfaz en español y notificaciones sin costo por SMS.

6. **Prueba gratuita sin riesgo** — Ofrece 10 días de prueba gratuita con todas las funciones, sin pedir tarjeta de crédito. El usuario puede cancelar cuando quiera.

7. **Un restaurante por cuenta** — Cada restaurante tiene su propio espacio aislado con su menú público y configuración. Ideal para que cada negocio maneje su marca.

8. **Dos fuentes de ingresos** — Suscripción mensual (paga el dueño del restaurante) más recargas de tokens de IA (paga por usar el escáner de facturas). Esto genera ingresos recurrentes.

9. **Notificaciones en tiempo real** — Cuando un cliente hace un pedido, el dueño recibe una notificación al instante, sin depender de SMS costosos.

---

## Debilidades (Internas, Negativas)

1. **Pocas pruebas automatizadas** — El sistema tiene algunas pruebas pero no las suficientes para garantizar que todo funciona correctamente después de cada cambio. Esto hace que cada actualización sea riesgosa.

2. **Código que podría estar mejor organizado** — Algunas funciones del panel de control todavía mezclan lógica de negocio con la presentación, lo que hace más difícil mantener y agregar nuevas funciones.

3. **Duplicación pequeña entre versiones web y móvil** — La plataforma tiene dos formas de acceder (escritorio y app móvil) que comparten la misma lógica central, pero aún hay pequeñas diferencias en cómo validan el acceso.

4. **Sin pruebas de seguridad** — No se han realizado pruebas para verificar que el sistema es resistente a ataques informáticos.

5. **Manejo de errores mejorable** — En algunas partes del sistema, cuando ocurre un error inesperado, no se registra adecuadamente la causa, lo que dificulta encontrar y solucionar problemas.

6. **Rendimiento mejorable en la app móvil** — Cuando un cliente accede al menú desde el celular, en algunos casos la información se carga producto por producto en lugar de todo a la vez, lo que puede hacer más lenta la experiencia.

7. **Clave de seguridad con respaldo fijo** — La plataforma tiene una clave secreta de respaldo hardcodeada. En desarrollo no es problema, pero si alguien la activa en producción sin configurar la clave correctamente, sería un riesgo de seguridad.


---

## Oportunidades (Externas, Positivas)

1. **Digitalización de restaurantes en Colombia** — Cada vez más restaurantes pequeños y medianos buscan menús digitales y pedidos online. El mercado está creciendo.

2. **Crecimiento de los pagos digitales** — Mercado Pago, Nequi y Daviplata están siendo adoptados masivamente en Colombia. Cada vez menos gente paga en efectivo.

3. **IA como ventaja competitiva** — El escáner de facturas con inteligencia artificial posiciona a Velzia como innovador frente a competidores que solo ofrecen menús digitales básicos.

4. **Precios accesibles** — Desde $30.000 COP al mes (~$7.50 USD). Un precio que cualquier restaurante pequeño puede pagar.

5. **Posibilidad de expandirse a otros países** — El modelo se puede replicar en Perú, México o Chile solo adaptando la pasarela de pagos.

6. **Nuevas funciones por desarrollar** — Inventario, gestión de empleados, reportes avanzados, integración con mensajerías para domicilios. Todas estas serían nuevas fuentes de ingresos.

7. **Tokens de IA como ingreso recurrente adicional** — Los restaurantes que usan el escáner de facturas pueden recargar tokens, generando ingresos fuera de la suscripción mensual.

8. **Crecimiento por recomendación** — Los dueños de restaurantes se conocen entre sí. Un programa de referidos podría traer clientes nuevos sin invertir en publicidad.

9. **Integración con WhatsApp** — Conectar la plataforma con WhatsApp Business API permitiría notificaciones y confirmaciones por el canal más usado en Colombia.

10. **Marketplace de restaurantes** — A futuro, se podría crear un directorio donde los clientes descubran nuevos restaurantes, similar a Rappi pero como plataforma para los dueños.

---

## Amenazas (Externas, Negativas)

1. **Competidores gratuitos** — Google My Business permite crear menú digital sin costo. Muchos restaurantes lo ven como suficiente.

2. **Gigantes del delivery** — Rappi e iFood tienen recursos para agregar menú digital autogestionado a su plataforma y dejar fuera a competidores pequeños.

3. **WhatsApp Business** — La mayoría de restaurantes en Colombia toman pedidos por WhatsApp sin costo. Es fácil quedarse con esa costumbre.

4. **Sensibilidad al precio** — $50.000 COP al mes puede ser mucho para una microempresa que está atravesando una crisis económica.

5. **Dependencia de servicios externos** — La plataforma depende de Clerk (autenticación), Cloudinary (imágenes), Mercado Pago (pagos) y ntfy.sh (notificaciones). Si alguno de estos cambia sus reglas o falla, afecta el servicio.

6. **Imitación por competidores** — La funcionalidad básica (menú digital + QR + pedidos) es fácil de copiar. La ventaja competitiva es temporal si no se innova.

7. **La deuda técnica puede frenar el crecimiento** — Si no se mejora la organización del código y las pruebas, cada nueva función será más lenta de desarrollar, dando ventaja a competidores más ágiles.

8. **Riesgos de seguridad informática** — Sin pruebas de seguridad, un ataque exitoso podría dañar la confianza de los clientes y el negocio.

9. **Crisis económicas** — En épocas de recesión, los restaurantes recortan gastos. Una suscripción SaaS es un gasto fácil de eliminar.

10. **Sin app para dueños** — Los dueños de restaurantes gestionan pedidos desde el navegador. Una app para ellos (no para los clientes) les daría acceso más rápido. Sin embargo, esto se puede solucionar activando la función PWA (web que funciona como app) que ya está instalada pero sin usar.

---

## Estrategias derivadas

### Crecimiento (Fortalezas + Oportunidades)
- Usar el escáner de facturas con IA como principal argumento de venta para atraer restaurantes que quieren digitalizarse.
- Aprovechar que ya tenemos Mercado Pago y precios en pesos para expandirnos a Perú, México y Chile.
- La prueba gratuita de 10 días sin tarjeta de crédito elimina la fricción de compra para restaurantes sensibles al precio.

### Mejora (Debilidades + Oportunidades)
- Invertir en mejorar las pruebas automatizadas y organizar mejor el código antes de crecer agresivamente.
- Eliminar las librerías que no se usan para aligerar el proyecto.
- Crear un README y estandarizar la documentación para facilitar la llegada de nuevos colaboradores.

### Defensa (Fortalezas + Amenazas)
- El escáner de facturas con IA es el único diferenciador real frente a Google My Business y WhatsApp. Invertir en mejorarlo continuamente.
- La protección contra bots y spam es una ventaja que los competidores no ofrecen. Usarlo como argumento de venta.
- La integración profunda con Colombia (Mercado Pago, precios en COP) protege contra competidores internacionales como Toast o Square.

### Supervivencia (Debilidades + Amenazas)
- La baja cobertura de pruebas combinada con código desorganizado es la amenaza más real. Un error en producción puede hacer que los restaurantes pierdan pedidos y se vayan a la competencia.
- Sin pruebas de seguridad, un ataque informático podría acabar con el negocio.
- La falta de app para dueños se puede resolver activando la función PWA que ya está lista, sin necesidad de desarrollar una app nativa.

---

## Conclusión

Orderfox/Velzia tiene un producto sólido con un diferenciador real frente a la competencia: el escáner de facturas con inteligencia artificial. Está bien posicionado para el mercado colombiano con precios accesibles, integración con Mercado Pago y un periodo de prueba sin riesgo.

La amenaza más urgente no son los competidores externos, sino mejorar la calidad del código y las pruebas automatizadas para poder crecer sin tropezar con errores. La prioridad recomendada es: **poner al día las pruebas y la organización del código → escalar el negocio agresivamente**.
