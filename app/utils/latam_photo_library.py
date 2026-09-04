"""
latam_photo_library — Libreria local de fotos curadas para platos LATAM/colombianos.

Unsplash y Pexels tienen catalogos anglosajones. Para comida tipica colombiana
(bandeja paisa, ajiaco, salchipapa, etc.) la API devuelve resultados irrelevantes.

Esta libreria resuelve el problema con un lookup de O(n) sobre ~80 entradas.
Las URLs son de Unsplash con parametros de calidad/formato fijo (estables).

Reglas:
- Las claves son minusculas y sin tildes para matching insensible.
- lookup() hace substring matching: "pollo sudado con papas" matchea "pollo".
- Las URLs apuntan a fotos con licencia libre (Unsplash License).
- Para agregar entradas: anadir clave -> URL curada. Sin deploy extra.
"""

_BASE = "https://images.unsplash.com/photo-{id}?q=80&w=800&auto=format&fit=crop&crop=center"


def _u(photo_id: str) -> str:
    return _BASE.format(id=photo_id)


# ~80 platos LATAM/colombianos curados manualmente.
# El lookup hace substring match (clave mas larga primero para mayor precision).
LATAM_LIBRARY: dict[str, str] = {
    # ── Colombiana clasica ──────────────────────────────────────────────
    "bandeja paisa":    _u("1565557244-65388e869022"),
    "ajiaco":           _u("1547592180-85f173990554"),
    "sancocho":         _u("1547592180-85f173990554"),
    "fritanga":         _u("1555939594-58d7cb561ad1"),
    "chicharron":       _u("1558030006-f6bff2fc5d50"),
    "morcilla":         _u("1544025162-d76694265947"),
    "chorizo":          _u("1544025162-d76694265947"),
    # ── Callejera / rapida ──────────────────────────────────────────────
    "salchipapa":       _u("1573080496219-bb080dd4f877"),
    "empanada":         _u("1601000938-db3abbd3e1d7"),
    "arepa de choclo":  _u("1601000938-db3abbd3e1d7"),
    "arepa":            _u("1601000938-db3abbd3e1d7"),
    "pandebono":        _u("1495474472287-4d71bcdd2085"),
    "bunuelo":          _u("1495474472287-4d71bcdd2085"),
    "almojabana":       _u("1495474472287-4d71bcdd2085"),
    "aborrajado":       _u("1601000938-db3abbd3e1d7"),
    "mazorca":          _u("1551754655-59e33e7c10e9"),
    "choclo":           _u("1551754655-59e33e7c10e9"),
    "chuzo":            _u("1544025162-d76694265947"),
    "pincho":           _u("1544025162-d76694265947"),
    # ── Sopas y caldos ──────────────────────────────────────────────────
    "caldo de costilla": _u("1547592180-85f173990554"),
    "changua":          _u("1547592180-85f173990554"),
    "sopa de lentejas": _u("1547592180-85f173990554"),
    "cuchuco":          _u("1547592180-85f173990554"),
    # ── Carnes ──────────────────────────────────────────────────────────
    "carne asada":      _u("1544025162-d76694265947"),
    "pechuga":          _u("1512621776951-a57141f2eefd"),
    "pollo a la brasa": _u("1562802378-074508538b76"),
    "pollo asado":      _u("1562802378-074508538b76"),
    "pollo":            _u("1562802378-074508538b76"),
    "costillas":        _u("1544025162-d76694265947"),
    "chuleta":          _u("1544025162-d76694265947"),
    "lomo":             _u("1544025162-d76694265947"),
    "cerdo":            _u("1544025162-d76694265947"),
    # ── Arroz y acompanantes ─────────────────────────────────────────────
    "arroz con pollo":  _u("1562802378-074508538b76"),
    "arroz con leche":  _u("1495474472287-4d71bcdd2085"),
    "arroz":            _u("1551754655-59e33e7c10e9"),
    "frijoles":         _u("1543339608-b70e5d1cee63"),
    "lentejas":         _u("1543339608-b70e5d1cee63"),
    "papa criolla":     _u("1573080496219-bb080dd4f877"),
    "papas fritas":     _u("1573080496219-bb080dd4f877"),
    "patacones":        _u("1601000938-db3abbd3e1d7"),
    "tajadas":          _u("1551754655-59e33e7c10e9"),
    # ── Mariscos y pescado ───────────────────────────────────────────────
    "cazuela de mariscos": _u("1559847844-5315695dadae"),
    "ceviche":          _u("1559847844-5315695dadae"),
    "pescado frito":    _u("1559847844-5315695dadae"),
    "camarones":        _u("1559847844-5315695dadae"),
    "mojarra":          _u("1559847844-5315695dadae"),
    # ── Postres y dulces ─────────────────────────────────────────────────
    "tres leches":      _u("1495474472287-4d71bcdd2085"),
    "torta":            _u("1495474472287-4d71bcdd2085"),
    "pastel":           _u("1495474472287-4d71bcdd2085"),
    "flan":             _u("1495474472287-4d71bcdd2085"),
    "natilla":          _u("1495474472287-4d71bcdd2085"),
    "dulce de leche":   _u("1495474472287-4d71bcdd2085"),
    # ── Bebidas ──────────────────────────────────────────────────────────
    "limonada de coco": _u("1495474472287-4d71bcdd2085"),
    "aguapanela":       _u("1495474472287-4d71bcdd2085"),
    "jugo de lulo":     _u("1495474472287-4d71bcdd2085"),
    # ── Internacionales frecuentes en Colombia ───────────────────────────
    "perro caliente":   _u("1568901346375-23c9450c58cd"),
    "hamburguesa":      _u("1568901346375-23c9450c58cd"),
    "hotdog":           _u("1568901346375-23c9450c58cd"),
    "pizza":            _u("1621996346565-e3dbc646d9a9"),
    "pasta":            _u("1621996346565-e3dbc646d9a9"),
    "sushi":            _u("1559339352-7d3e8b8a5e1e"),
    "tacos":            _u("1565557244-65388e869022"),
    "ensalada":         _u("1512621776951-a57141f2eefd"),
    "sandwich":         _u("1571114865113-04578cf9c438"),
    "sandwich de queso": _u("1571114865113-04578cf9c438"),
    "sandwich cubano":  _u("1705537459006-f4acbd93c5a3"),
    "sandwich misto":   _u("1603903631889-b5f3ba4d5b9b"),
    "burrito":          _u("1565557244-65388e869022"),
    "wrap":             _u("1568901346375-23c9450c58cd"),
}


def lookup(product_name: str) -> str | None:
    """
    Busca foto curada para el nombre del producto via substring matching.

    Prioridad: coincidencia exacta > substring (clave mas larga primero).
    Retorna URL o None si no hay match.

    Ejemplos:
        lookup("Salchipapa Especial con Queso") -> URL de salchipapa
        lookup("Pollo asado con papas") -> URL de pollo asado
        lookup("Xyz desconocido") -> None
    """
    normalized = _normalize(product_name)

    # Coincidencia exacta
    if normalized in LATAM_LIBRARY:
        return LATAM_LIBRARY[normalized]

    # Substring — preferir claves mas largas (mas especificas)
    for key in sorted(LATAM_LIBRARY.keys(), key=len, reverse=True):
        if key in normalized:
            return LATAM_LIBRARY[key]

    return None


def _normalize(text: str) -> str:
    """Minusculas + elimina tildes/dieresis para matching insensible."""
    table = str.maketrans(
        "\xe1\xe9\xed\xf3\xfa\xe0\xe8\xec\xf2\xf9\xe4\xeb\xef\xf6\xfc\xf1",
        "aeiouaeiouaeioun",
    )
    return text.lower().translate(table)
