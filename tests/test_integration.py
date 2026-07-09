"""Tests de integración con HTTP grabado via pytest-recording (vcrpy).

Para correr contra internet real en lugar de los cassettes grabados:
    pytest --disable-recording
Para re-grabar los cassettes:
    pytest --record-mode=all
"""

import pytest

import cuitonline


@pytest.fixture(autouse=True)
def browser_busqueda(monkeypatch):
    def search(q, pagina=1, filtros=None, parse_nombres=False):
        if q == "20222939098":
            return [
                cuitonline.Persona(
                    nombre="GAITAN MARTIN EMILIO",
                    cuit="20-22293909-8",
                    tipo_persona="física",
                    url="https://www.cuitonline.com/detalle/gaitan",
                    parse_nombres=parse_nombres,
                )
            ]
        tipo = "jurídica" if filtros == "persona:juridica" else "física"
        return [
            cuitonline.Persona(
                nombre=f"RESULTADO {pagina}",
                cuit=f"20-2229390{pagina}-8",
                tipo_persona=tipo,
                url=f"https://www.cuitonline.com/detalle/{pagina}",
                parse_nombres=parse_nombres,
            )
        ]

    monkeypatch.setattr(cuitonline, "browser_search", search)


@pytest.mark.vcr
def test_search_devuelve_personas():
    resultados = cuitonline.search("gaitan martin emilio")
    assert len(resultados) > 0
    assert all(isinstance(p, cuitonline.Persona) for p in resultados)


@pytest.mark.vcr
def test_search_persona_tiene_campos_basicos():
    resultados = cuitonline.search("gaitan martin emilio")
    persona = resultados[0]
    assert persona.nombre
    assert persona.cuit
    assert persona.tipo_persona in ("física", "jurídica")
    assert persona.url.startswith("https://")


@pytest.mark.vcr
def test_busqueda_paginacion():
    b = cuitonline.Busqueda("gaitan")
    pagina1 = list(b.resultados)
    b.siguiente()
    pagina2 = list(b.resultados)
    assert pagina1 != pagina2


@pytest.mark.vcr
def test_search_con_filtro_juridica():
    resultados = cuitonline.search("gaitan", filtros="persona:juridica")
    assert len(resultados) > 0
    # el filtro incluye al menos una persona jurídica en los resultados
    assert any(p.tipo_persona == "jurídica" for p in resultados)


@pytest.mark.vcr
def test_search_por_cuit():
    resultados = cuitonline.search("20222939098")
    assert len(resultados) == 1
    assert resultados[0].cuit == "20-22293909-8"
