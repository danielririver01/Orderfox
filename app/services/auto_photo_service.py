"""
auto_photo_service.py — Asignacion automatica de fotos a productos sin imagen.

Flujo:
1. POST /api/products crea el producto -> llama enqueue() (no bloquea el request).
2. Hilo background: keyword extraction (Gemini Flash) -> LATAM library -> Unsplash API.
3. Descarga la mejor foto, la sube a Cloudinary con smart crop 1:1.
4. UPDATE products SET image_url, image_source, is_auto_image, suggested_image_pool.

Decisiones de disenio:
- threading.Thread con app_context: igual que APScheduler, zero dependencias extra.
- Gemini 1.5 Flash para extraccion de keywords: rapido y economico.
- Pool de 5 fotos guardado en suggested_image_pool (JSON) para 1-Click Swap sin API calls.
- Unicidad por restaurante: filtro de fotos ya usadas antes de asignar (max 2 API calls por producto).
- Fallback silencioso: si falla cualquier nivel, el producto queda sin imagen (no error).
"""

import json
import logging
import threading
import io
import requests

from flask import current_app

from app.models import db, Product
from app.utils import latam_photo_library

logger = logging.getLogger(__name__)


class AutoPhotoService:
    """Asigna fotos automaticamente a productos sin imagen."""

    # ── Public API ─────────────────────────────────────────────────────

    @staticmethod
    def enqueue(app, product_id: int, product_name: str, restaurant_id: int) -> None:
        """
        Lanza el proceso de auto-asignacion en un hilo background.
        Retorna inmediatamente; no bloquea el request HTTP.

        Args:
            app: La instancia de Flask (current_app._get_current_object()).
            product_id: ID del producto recien creado.
            product_name: Nombre del producto para generar el keyword visual.
            restaurant_id: ID del restaurante (para filtro de unicidad).
        """
        # Verificar master switch
        if not app.config.get('AUTOPHOTO_ENABLED', True):
            return

        # Verificar que haya al menos Unsplash key (si no, el proceso es no-op)
        has_unsplash = bool(app.config.get('UNSPLASH_ACCESS_KEY'))
        has_latam = True  # siempre disponible (libreria local)
        if not has_unsplash and not has_latam:
            return

        t = threading.Thread(
            target=AutoPhotoService._run,
            args=(app, product_id, product_name, restaurant_id),
            daemon=True,
            name=f"autophoto-{product_id}",
        )
        t.start()
        logger.debug(f"AutoPhoto: enqueued for product {product_id} ({product_name!r})")

    # ── Background worker ──────────────────────────────────────────────

    @staticmethod
    def _run(app, product_id: int, product_name: str, restaurant_id: int) -> None:
        """Proceso principal en hilo background con app_context."""
        with app.app_context():
            try:
                AutoPhotoService._process(product_id, product_name, restaurant_id)
            except Exception as e:
                logger.error(
                    f"AutoPhoto: unexpected error for product {product_id}: {e}",
                    exc_info=True,
                )

    @staticmethod
    def _process(product_id: int, product_name: str, restaurant_id: int) -> None:
        """
        Pipeline de asignacion de foto:
        Nivel 0 (re-check): Si el producto ya tiene imagen (subida manualmente
                            mientras el hilo arrancaba), no hacer nada.
        Nivel 1 (LATAM library): Lookup local sin API calls.
        Nivel 2 (Unsplash): Busqueda via API con filtro de unicidad (max 2 calls).
        Nivel 3 (fallback): Sin imagen — silencioso, no error.
        """
        # Re-check: el usuario pudo haber subido imagen manualmente
        product = db.session.get(Product, product_id)
        if not product:
            logger.warning(f"AutoPhoto: product {product_id} not found, skipping")
            return
        if product.image_url:
            logger.debug(f"AutoPhoto: product {product_id} already has image, skipping")
            return

        # Nivel 1: LATAM library (zero API calls, instantaneo)
        local_url = latam_photo_library.lookup(product_name)
        if local_url:
            # Buscar alternativas en Unsplash para llenar el pool del 🎲
            keyword = AutoPhotoService._extract_keyword(product_name)
            if not keyword:
                keyword = product_name
            used_urls = AutoPhotoService._get_used_urls(restaurant_id)
            pool = AutoPhotoService._unsplash_search(keyword, count=5)
            # Excluir la URL ya asignada desde la library
            local_base = local_url.split("?")[0]
            alternatives = [
                url for url in pool
                if url.split("?")[0] not in used_urls and url.split("?")[0] != local_base
            ]
            AutoPhotoService._assign(product, local_url, 'local_library', alternatives)
            logger.info(
                f"AutoPhoto: product {product_id} assigned from local_library "
                f"(pool_size={len(alternatives)})"
            )
            return

        # Nivel 2: Unsplash API con filtro de unicidad
        keyword = AutoPhotoService._extract_keyword(product_name)
        if not keyword:
            keyword = product_name  # fallback: usar nombre original

        used_urls = AutoPhotoService._get_used_urls(restaurant_id)

        # Intento 1: busqueda con keyword exacto
        pool = AutoPhotoService._unsplash_search(keyword, count=5)
        available = [
            url for url in pool
            if url.split("?")[0] not in used_urls
        ]

        # Intento 2: busqueda con keyword de categoria generica (sin Gemini extra)
        if not available:
            category_keyword = AutoPhotoService._extract_category(product_name)
            pool2 = AutoPhotoService._unsplash_search(category_keyword, count=5)
            available = [
                url for url in pool2
                if url.split("?")[0] not in used_urls
            ]

        if available:
            best_url = available[0]
            alternatives = available[1:]
            # Guardar URL base de Unsplash (sin params) para unicidad
            unsplash_base = best_url.split("?")[0]
            # Subir la mejor foto a Cloudinary con smart crop
            cloudinary_url = AutoPhotoService._upload_to_cloudinary(best_url)
            final_url = cloudinary_url or best_url  # fallback: URL directa de Unsplash
            AutoPhotoService._assign(
                product, final_url, 'unsplash', alternatives,
                unsplash_source_url=unsplash_base,
            )
            logger.info(
                f"AutoPhoto: product {product_id} assigned from unsplash "
                f"(keyword={keyword!r}, pool_size={len(alternatives)}, "
                f"restaurant={restaurant_id})"
            )
            return

        # Nivel 3: No foto encontrada — silencioso
        logger.info(
            f"AutoPhoto: no image found for product {product_id} "
            f"({product_name!r}), keyword={keyword!r}, restaurant={restaurant_id}"
        )

    # ── Keyword extraction (Gemini 1.5 Flash) ─────────────────────────

    @staticmethod
    def _extract_keyword(product_name: str) -> str | None:
        """
        Extrae 3-5 palabras clave visuales del nombre del producto usando Gemini Flash.

        Ejemplo:
            Input:  "Promo 2x1: Hamburguesa Doble Queso + Papas Francesas"
            Output: "double cheeseburger french fries"

        Si falla (sin API key, error de red, etc.) retorna None para que el
        llamador use el nombre original como fallback.
        """
        api_key = current_app.config.get('GEMINI_API_KEY')
        if not api_key:
            logger.debug("AutoPhoto: GEMINI_API_KEY not set, skipping LLM extraction")
            return None

        prompt = (
            "You are a visual keyword extractor for a food photo search engine.\n"
            "Given a food product name (possibly in Spanish, with promotions or extra text), "
            "extract only the 3-5 most visually descriptive English words that describe "
            "the core food item. Focus on what the dish LOOKS LIKE in a photo.\n\n"
            "Rules:\n"
            "- Remove promo text (2x1, Especial, Promo, Combo, etc.)\n"
            "- Translate to English\n"
            "- Return ONLY the keywords, no explanation\n\n"
            f"Product name: {product_name}\n"
            "Keywords:"
        )

        try:
            url = (
                "https://generativelanguage.googleapis.com/v1beta/models/"
                f"gemini-1.5-flash:generateContent?key={api_key}"
            )
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.1,
                    "maxOutputTokens": 30,
                },
            }
            resp = requests.post(url, json=payload, timeout=8)
            resp.raise_for_status()
            data = resp.json()
            keyword = (
                data.get("candidates", [{}])[0]
                .get("content", {})
                .get("parts", [{}])[0]
                .get("text", "")
                .strip()
                .lower()
            )
            # Validar que la respuesta tenga sentido (no vacia, no muy larga)
            if keyword and len(keyword) < 100:
                return keyword
            return None
        except Exception as e:
            logger.warning(f"AutoPhoto: Gemini keyword extraction failed: {e}")
            return None

    # ── Uniqueness helpers ──────────────────────────────────────────────

    @staticmethod
    def _get_used_urls(restaurant_id: int) -> set:
        """
        Retorna el set de URLs base de Unsplash ya en uso en este restaurante.
        1 sola query SELECT, siempre preciso (incluye uploads manuales si tienen
        unsplash_source_url).
        """
        rows = (
            db.session.query(Product.unsplash_source_url)
            .filter(
                Product.restaurant_id == restaurant_id,
                Product.unsplash_source_url.isnot(None),
            )
            .all()
        )
        return {row[0] for row in rows}

    @staticmethod
    def _extract_category(product_name: str) -> str:
        """
        Devuelve una keyword de categoria visual generica cuando el keyword exacto
        agoto su pool. Usa la primera palabra del keyword como base.

        Ejemplos:
            "double cheeseburger french fries"  -> "cheeseburger food"
            "grilled chicken rice"              -> "chicken food"
            "tropical fruit smoothie"           -> "smoothie drink"
        """
        # Usar keyword si ya esta extraido, sino traducir nombre basico
        words = product_name.split()
        if words:
            # Tomar las primeras 2 palabras significativas + "food"
            core = " ".join(w for w in words[:2] if len(w) > 2)
            if core:
                return f"{core} food"
        return "restaurant food plate"

    # ── Unsplash search ────────────────────────────────────────────────

    @staticmethod
    def _unsplash_search(keyword: str, count: int = 5) -> list[str]:
        """
        Busca fotos en Unsplash API.

        Retorna lista de URLs de fotos (tamano 800px, formato auto).
        Lista vacia si no hay resultados o si falla la API.
        """
        access_key = current_app.config.get('UNSPLASH_ACCESS_KEY')
        if not access_key:
            logger.debug("AutoPhoto: UNSPLASH_ACCESS_KEY not set, skipping")
            return []

        try:
            resp = requests.get(
                "https://api.unsplash.com/search/photos",
                params={
                    "query": keyword,
                    "per_page": count,
                    "orientation": "squarish",  # preferir fotos cuadradas
                    "content_filter": "high",   # solo contenido apto
                },
                headers={"Authorization": f"Client-ID {access_key}"},
                timeout=10,
            )
            resp.raise_for_status()
            results = resp.json().get("results", [])

            urls = []
            for photo in results:
                url = photo.get("urls", {}).get("regular")  # 1080px
                if url:
                    # Forzar parametros para consistencia: 800x800, webp, crop centro
                    url = url.split("?")[0] + "?q=80&w=800&h=800&fit=crop&crop=center&fm=webp"
                    urls.append(url)

            return urls
        except Exception as e:
            logger.warning(f"AutoPhoto: Unsplash search failed (keyword={keyword!r}): {e}")
            return []

    # ── Cloudinary upload ──────────────────────────────────────────────

    @staticmethod
    def _upload_to_cloudinary(image_url: str) -> str | None:
        """
        Descarga la foto de Unsplash y la sube a Cloudinary con:
        - Smart crop 1:1 centrado en el objeto (gravity=auto)
        - Formato auto (webp en navegadores modernos)
        - Folder: velzia/products/auto/
        - Marcada con tag 'autophoto' para auditoria

        Retorna la URL segura de Cloudinary o None si falla.
        """
        try:
            import cloudinary
            import cloudinary.uploader

            cloudinary.config(
                cloud_name=current_app.config.get('CLOUDINARY_CLOUD_NAME'),
                api_key=current_app.config.get('CLOUDINARY_API_KEY'),
                api_secret=current_app.config.get('CLOUDINARY_API_SECRET'),
                secure=True,
            )

            # Descargar la imagen de Unsplash
            img_resp = requests.get(image_url, timeout=15, stream=True)
            img_resp.raise_for_status()
            img_data = io.BytesIO(img_resp.content)

            # Subir a Cloudinary con smart crop
            result = cloudinary.uploader.upload(
                img_data,
                folder="velzia/products/auto",
                resource_type="image",
                tags=["autophoto"],
                transformation=[
                    {
                        "width": 800,
                        "height": 800,
                        "crop": "fill",
                        "gravity": "auto",  # smart crop: centra en el objeto
                        "quality": "auto:good",
                        "fetch_format": "auto",  # webp en navegadores modernos
                    }
                ],
            )
            return result.get("secure_url")
        except Exception as e:
            logger.warning(f"AutoPhoto: Cloudinary upload failed: {e}")
            return None

    # ── DB update ──────────────────────────────────────────────────────

    @staticmethod
    def _assign(
        product: Product,
        url: str,
        source: str,
        pool: list[str],
        unsplash_source_url: str | None = None,
    ) -> None:
        """
        Actualiza el producto con la foto asignada.
        Solo actualiza si el producto aun no tiene imagen (evita race condition).

        Args:
            unsplash_source_url: URL base de Unsplash (sin params) para unicidad.
                                 Solo se guarda cuando source='unsplash'.
        """
        try:
            # Re-leer el producto para evitar race condition con upload manual
            fresh = db.session.get(Product, product.id)
            if not fresh or fresh.image_url:
                logger.debug(
                    f"AutoPhoto: product {product.id} already has image "
                    "after assignment attempt, skipping"
                )
                return

            fresh.image_url = url
            fresh.image_source = source
            fresh.is_auto_image = True
            # Para imágenes de LATAM library sin pool, crear pool vacío para que el
            # botón 🎲 aparezca (indica que la imagen fue auto-asignada)
            fresh.suggested_image_pool = json.dumps(pool) if pool else None
            if unsplash_source_url:
                fresh.unsplash_source_url = unsplash_source_url
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"AutoPhoto: DB assignment failed for product {product.id}: {e}")

    # ── 1-Click Swap ───────────────────────────────────────────────────

    @staticmethod
    def swap_suggested(product_id: int, restaurant_id: int) -> dict:
        """
        Rota al siguiente URL del suggested_image_pool sin llamadas externas.

        Comportamiento:
        - Toma el primer URL del pool, lo asigna como imagen principal.
        - El URL anterior se descarta (no vuelve al pool).
        - Si el pool queda vacio, is_auto_image se mantiene True pero el boton
          de swap desaparece en el frontend.

        Retorna dict con 'success', 'image_url', y 'pool_remaining'.
        """
        product = Product.query.filter_by(
            id=product_id, restaurant_id=restaurant_id
        ).first()
        if not product:
            return {'success': False, 'error': 'Producto no encontrado'}

        if not product.is_auto_image:
            return {'success': False, 'error': 'Este producto no tiene fotos alternativas'}

        pool = []
        if product.suggested_image_pool:
            try:
                pool = json.loads(product.suggested_image_pool)
            except (json.JSONDecodeError, TypeError):
                pool = []

        if not pool:
            # Pool vacío: buscar alternativas en Unsplash ahora
            keyword = AutoPhotoService._extract_keyword(product.name)
            if not keyword:
                keyword = product.name
            used_urls = AutoPhotoService._get_used_urls(restaurant_id)
            # Excluir la imagen actual del producto
            current_base = (product.image_url or "").split("?")[0]
            fresh_pool = AutoPhotoService._unsplash_search(keyword, count=5)
            pool = [
                url for url in fresh_pool
                if url.split("?")[0] not in used_urls and url.split("?")[0] != current_base
            ]
            if not pool:
                return {
                    'success': True,
                    'image_url': product.image_url,
                    'pool_remaining': 0,
                    'message': 'No hay mas fotos alternativas',
                }
            # Guardar el pool para futuros clicks
            try:
                product.suggested_image_pool = json.dumps(pool)
                db.session.commit()
            except Exception:
                db.session.rollback()

        # Rotar: el primer URL del pool pasa a ser la imagen principal
        new_url = pool.pop(0)
        try:
            product.image_url = new_url
            product.suggested_image_pool = json.dumps(pool) if pool else None
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"AutoPhoto swap failed for product {product_id}: {e}")
            return {'success': False, 'error': 'Error al cambiar la foto'}

        return {
            'success': True,
            'image_url': new_url,
            'pool_remaining': len(pool),
        }
