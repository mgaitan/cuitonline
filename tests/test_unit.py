"""Tests unitarios de funciones puras y modelos."""

import pytest
from bs4 import BeautifulSoup as BS4

import cuitonline
from cuitonline import (
    ContentUnavailableError,
    Persona,
    Sopita,
    _extraer_tipo_persona,
    _is_cloudflare_challenge,
    _parsear_filtros,
    _persona_a_dict,
    _search_url,
    browser_search,
)


def _make_hit(tipo: str) -> BS4:
    html = f"""<div class="hit">
      <div class="doc-facets">
        <span class="linea-cuit-persona"><span class="cuit">20-123-4</span></span>
        <span class="bullet">•</span>
        {tipo}
      </div>
    </div>"""
    return BS4(html, "html.parser").select_one(".hit")


class TestExtraerTipoPersona:
    def test_fisica(self):
        assert (
            _extraer_tipo_persona(_make_hit("Persona Física ( masculino )")) == "física"
        )

    def test_fisica_femenino(self):
        assert (
            _extraer_tipo_persona(_make_hit("Persona Física ( femenino )")) == "física"
        )

    def test_juridica(self):
        assert _extraer_tipo_persona(_make_hit("Persona Jurídica")) == "jurídica"

    def test_fallback_fisica(self):
        hit = BS4(
            '<div class="hit"><div class="doc-facets"></div></div>', "html.parser"
        ).select_one(".hit")
        assert _extraer_tipo_persona(hit) == "física"


class TestParsearFiltros:
    def test_sin_filtros_devuelve_default(self):
        assert _parsear_filtros(None) == [("f5[]", "persona:fisica")]

    def test_string_vacio_devuelve_default(self):
        assert _parsear_filtros("") == [("f5[]", "persona:fisica")]

    def test_persona_juridica_va_a_f5(self):
        assert _parsear_filtros("persona:juridica") == [("f5[]", "persona:juridica")]

    def test_ganancias_va_a_f0(self):
        assert _parsear_filtros("ganancias:no_inscripto") == [
            ("f0[]", "ganancias:no_inscripto")
        ]

    def test_iva_va_a_f1(self):
        assert _parsear_filtros("iva:iva_exento") == [("f1[]", "iva:iva_exento")]

    def test_monotributo_va_a_f2(self):
        assert _parsear_filtros("monotributo:inscripto") == [
            ("f2[]", "monotributo:inscripto")
        ]

    def test_empleador_va_a_f4(self):
        assert _parsear_filtros("empleador:si") == [("f4[]", "empleador:si")]

    def test_nacionalidad_va_a_f6(self):
        assert _parsear_filtros("nacionalidad:argentina") == [
            ("f6[]", "nacionalidad:argentina")
        ]

    def test_multiples_filtros_distintas_facetas(self):
        result = _parsear_filtros("persona:juridica,iva:iva_exento")
        assert result == [("f5[]", "persona:juridica"), ("f1[]", "iva:iva_exento")]

    def test_filtros_con_espacios(self):
        result = _parsear_filtros("persona:juridica, iva:iva_exento")
        assert result == [("f5[]", "persona:juridica"), ("f1[]", "iva:iva_exento")]


class TestHTTP:
    def test_search_url_usa_ruta_nueva_y_escapa_criterio(self):
        assert _search_url("Lionel Scaloni/1") == (
            "https://www.cuitonline.com/search/Lionel%20Scaloni%2F1"
        )

    def test_challenge_cloudflare_se_reconoce(self):
        assert _is_cloudflare_challenge("<script>window._cf_chl_opt = {}</script>")

    def test_recursos_cloudflare_normales_no_son_un_challenge(self):
        html = "<script src='https://challenges.cloudflare.com/script.js'></script>"
        assert not _is_cloudflare_challenge(html)

    def test_browser_search_usa_el_html_del_navegador(self, monkeypatch):
        captured = {}
        html = """<div class="hit">
          <div class="linea-cuit-persona"><span class="cuit">20-123-4</span></div>
          <div class="doc-facets">Persona Física</div>
          <div class="denominacion"><a href="persona/prueba"><h2>PRUEBA</h2></a></div>
        </div>"""

        def get(url, params):
            captured.update(url=url, params=params)
            return html

        monkeypatch.setattr(cuitonline, "_browser_get", get)

        assert browser_search("prueba")[0].nombre == "PRUEBA"
        assert captured == {
            "url": "https://www.cuitonline.com/search/prueba",
            "params": [("pn", "1"), ("f5[]", "persona:fisica")],
        }

    def test_serializar_resultado_no_pide_detalles(self, monkeypatch):
        persona = Persona(
            nombre="PRUEBA",
            cuit="20-123-4",
            tipo_persona="física",
            url="https://www.cuitonline.com/persona/prueba",
        )

        def browser_unexpected(*args, **kwargs):
            raise AssertionError("No debe pedir detalles al serializar el resultado")

        monkeypatch.setattr(cuitonline, "_browser_get", browser_unexpected)

        result = _persona_a_dict(persona)
        assert result["nombre"] == "PRUEBA"
        assert "direccion" not in result

    def test_detalles_usan_el_navegador(self, monkeypatch):
        html = """
        <span itemprop="gender">Masculino</span>
        <span itemprop="streetAddress">Calle 1</span>
        <span itemprop="addressRegion">Cordoba</span>
        <span itemprop="addressLocality">Capital</span>
        <span itemprop="nationality">Argentina</span>
        <li>Monotributista <span>A</span></li>
        <li>Empleador <span>Sí</span></li>
        """
        persona = Persona(
            nombre="PRUEBA",
            cuit="20-123-4",
            tipo_persona="física",
            url="https://www.cuitonline.com/detalle/prueba",
        )
        monkeypatch.setattr(cuitonline, "_browser_get", lambda url, params: html)

        assert persona.direccion == "Calle 1"
        assert persona.empleador is True

    def test_detalles_restringidos_informan_el_estado(self, monkeypatch):
        persona = Persona(
            nombre="PRUEBA",
            cuit="20-123-4",
            tipo_persona="física",
            url="https://www.cuitonline.com/detalle/prueba",
        )
        monkeypatch.setattr(
            cuitonline,
            "_browser_get",
            lambda url, params: "<title>.:: ERROR 404 ::.</title>",
        )

        with pytest.raises(ContentUnavailableError):
            _ = persona.direccion


class TestPersona:
    @pytest.fixture
    def persona_fisica(self):
        return Persona(
            nombre="GAITAN MARTIN EMILIO",
            cuit="20-22293909-8",
            tipo_persona="física",
            url="https://www.cuitonline.com/persona/gaitan/123",
            parse_nombres=True,
        )

    @pytest.fixture
    def persona_juridica(self):
        return Persona(
            nombre="EMPRESA SA",
            cuit="30-12345678-9",
            tipo_persona="jurídica",
            url="https://www.cuitonline.com/persona/empresa/456",
        )

    def test_dni_persona_fisica(self, persona_fisica):
        assert persona_fisica.dni == 22293909

    def test_dni_persona_juridica_es_none(self, persona_juridica):
        assert persona_juridica.dni is None

    def test_nombre_pila_persona_fisica(self, persona_fisica):
        assert persona_fisica.nombre_pila == "MARTIN"

    def test_apellido_persona_fisica(self, persona_fisica):
        assert persona_fisica.apellido == "GAITAN"

    def test_nombre_pila_sin_nameparser_es_none(self, monkeypatch):
        monkeypatch.setattr(cuitonline, "HumanName", None)
        p = Persona(
            nombre="GAITAN MARTIN EMILIO",
            cuit="20-22293909-8",
            tipo_persona="física",
            url="https://www.cuitonline.com/persona/gaitan/123",
            parse_nombres=True,
        )
        assert p.nombre_pila is None
        assert p.apellido is None

    def test_nombre_pila_sin_parse_nombres_es_none(self):
        p = Persona(
            nombre="GAITAN MARTIN EMILIO",
            cuit="20-22293909-8",
            tipo_persona="física",
            url="https://www.cuitonline.com/persona/gaitan/123",
        )
        assert p.nombre_pila is None
        assert p.apellido is None

    def test_nombre_pila_persona_juridica_es_none(self, persona_juridica):
        assert persona_juridica.nombre_pila is None

    def test_apellido_persona_juridica_es_none(self, persona_juridica):
        assert persona_juridica.apellido is None


class TestSopita:
    def test_extract_por_selector(self):
        html = "<html><span itemprop='addressRegion'>Buenos Aires</span></html>"
        soup = Sopita(html, "html.parser")
        assert soup._extract("itemprop", "addressRegion") == "Buenos Aires"

    def test_extract_por_css(self):
        html = "<html><h2 class='titulo'>Hola</h2></html>"
        soup = Sopita(html, "html.parser")
        assert soup._extract("h2.titulo") == "Hola"

    def test_extract_elemento_inexistente_devuelve_none(self):
        soup = Sopita("<html></html>", "html.parser")
        assert soup._extract("itemprop", "inexistente") is None
