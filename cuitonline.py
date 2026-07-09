"""
CLI y biblioteca Python de cuitonline.com. No oficial.
"""

import argparse
import json
import os
import shutil
import signal
import socket
import subprocess
import time
from functools import cached_property
from pathlib import Path
from typing import List, Optional
from urllib.parse import quote, urlencode

import requests
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field, computed_field

try:
    from nameparser import HumanName
except ImportError:
    HumanName = None

base_url = "https://www.cuitonline.com"
_browser_profile = Path(
    os.environ.get(
        "CUITONLINE_BROWSER_PROFILE",
        Path.home() / ".local" / "share" / "cuitonline" / "browser-profile",
    )
)

__version__ = "0.3.0"

_DETAIL_FIELDS = {
    "_details",
    "genero",
    "direccion",
    "provincia",
    "localidad",
    "nacionalidad",
    "monotributo",
    "empleador",
}


class CloudflareChallengeError(RuntimeError):
    """El sitio pidió una verificación interactiva que requests no puede resolver."""


class ContentUnavailableError(RuntimeError):
    """El sitio no entregó la página de detalle para la sesión actual."""


class BrowserSupportError(RuntimeError):
    """No se pudo iniciar el navegador requerido para la sesión interactiva."""


def _is_cloudflare_challenge(html: str) -> bool:
    """Reconoce la página de desafío, no recursos de Cloudflare del sitio normal."""
    return (
        "window._cf_chl_opt" in html
        or 'id="challenge-error-text"' in html
        or "<title>Just a moment...</title>" in html
    )


def _search_url(q: str) -> str:
    """Devuelve la ruta de búsqueda actual del sitio."""
    return f"{base_url}/search/{quote(q, safe='')}"


def _parse_search_results(html: str, parse_nombres: bool = False) -> List["Persona"]:
    soup = BeautifulSoup(html, "html.parser")
    resultados = []
    for item in soup.select(".hit"):
        cuit = item.select_one(".linea-cuit-persona .cuit").get_text(strip=True)
        persona = Persona(
            nombre=item.select_one(".denominacion h2").get_text(strip=True),
            cuit=cuit,
            tipo_persona=_extraer_tipo_persona(item),
            url=f"{base_url}/{item.select_one('.denominacion a')['href']}",
            parse_nombres=parse_nombres,
        )
        resultados.append(persona)
    return resultados


def _persona_a_dict(persona: "Persona", detalles: bool = False) -> dict:
    """Serializa un resultado; los detalles se consultan sólo bajo pedido."""
    return persona.model_dump(exclude=None if detalles else _DETAIL_FIELDS)


def _playwright():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as error:
        raise BrowserSupportError(
            "El modo navegador requiere instalar cuitonline con soporte de navegador."
        ) from error

    return sync_playwright()


def _free_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def _chrome_executable() -> str:
    configured = os.environ.get("CUITONLINE_CHROME")
    candidates = [configured] if configured else []
    candidates.extend(["google-chrome", "chromium", "chromium-browser"])
    for candidate in candidates:
        if candidate and (executable := shutil.which(candidate)):
            return executable
    raise BrowserSupportError(
        "No se encontró Google Chrome. Definí CUITONLINE_CHROME con su ejecutable."
    )


def _start_chrome(target: str) -> tuple[subprocess.Popen, str]:
    """Inicia Chrome normal; Playwright no participa de su lanzamiento."""
    _browser_profile.mkdir(mode=0o700, parents=True, exist_ok=True)
    port = _free_local_port()
    endpoint = f"http://127.0.0.1:{port}"
    process = subprocess.Popen(
        [
            _chrome_executable(),
            f"--user-data-dir={_browser_profile}",
            "--remote-debugging-address=127.0.0.1",
            f"--remote-debugging-port={port}",
            "--no-first-run",
            "--no-default-browser-check",
            target,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if process.poll() is not None:
            break
        try:
            response = requests.get(f"{endpoint}/json/version", timeout=0.2)
            if response.ok:
                return process, endpoint
        except requests.RequestException:
            pass
        time.sleep(0.1)
    _stop_chrome(process)
    raise BrowserSupportError("Google Chrome no pudo iniciarse con el perfil de cuitonline.")


def _stop_chrome(process: subprocess.Popen) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait()


def _connect_to_chrome(endpoint: str):
    playwright = _playwright().start()
    try:
        browser = playwright.chromium.connect_over_cdp(endpoint)
    except Exception as error:
        playwright.stop()
        raise BrowserSupportError("No se pudo conectar al Chrome abierto.") from error
    return playwright, browser


def _chrome_page(browser):
    for context in browser.contexts:
        if context.pages:
            return context.pages[-1]
    raise BrowserSupportError("Chrome no abrió la página solicitada.")


def _browser_get(url: str, params: list[tuple[str, str]]) -> str:
    query = urlencode(params)
    target = f"{url}?{query}" if query else url
    process, endpoint = _start_chrome(target)
    playwright = browser = None
    try:
        playwright, browser = _connect_to_chrome(endpoint)
        page = _chrome_page(browser)
        page.wait_for_load_state("domcontentloaded", timeout=60_000)
        return page.content()
    finally:
        if browser:
            browser.close()
        if playwright:
            playwright.stop()
        _stop_chrome(process)


def browser_login(q: str = "cuit") -> None:
    """Abre Chrome normal para que el usuario complete el desafío de Cloudflare."""
    process, endpoint = _start_chrome(_search_url(q))
    playwright = browser = None
    try:
        input(
            "Completá la verificación o buscá el criterio mostrado en Chrome y, "
            "cuando veas resultados, "
            "presioná Enter para guardar la sesión. "
        )
        playwright, browser = _connect_to_chrome(endpoint)
        page = _chrome_page(browser)
        html = page.content()
        if _is_cloudflare_challenge(html):
            raise CloudflareChallengeError(
                "La verificación no quedó completada. Volvé a intentarlo y esperá "
                "hasta ver los resultados de búsqueda antes de presionar Enter."
            )
    finally:
        if browser:
            browser.close()
        if playwright:
            playwright.stop()
        _stop_chrome(process)


def browser_search(
    q: str,
    pagina: int = 1,
    filtros: Optional[str] = None,
    parse_nombres: bool = False,
) -> List["Persona"]:
    """Busca desde el perfil Chrome autorizado por el usuario."""
    params = [("pn", str(pagina))] + _parsear_filtros(filtros)
    html = _browser_get(_search_url(q), params)
    if _is_cloudflare_challenge(html):
        raise CloudflareChallengeError(
            "Cloudflare todavía requiere verificación. Ejecutá `cuitonline --login` "
            "en una sesión gráfica y completala antes de buscar.",
        )
    return _parse_search_results(html, parse_nombres=parse_nombres)


class Sopita(BeautifulSoup):
    def _extract(self, selector_or_attr: str, value: Optional[str] = None):
        """
        Extrae texto de un elemento HTML
        """
        if (
            element := self.find(attrs={selector_or_attr: value})
            if value
            else self.select_one(selector_or_attr)
        ):
            return element.get_text(strip=True)


class Persona(BaseModel):
    nombre: str
    cuit: str
    tipo_persona: str
    url: str
    parse_nombres: bool = Field(default=False, exclude=True)

    @computed_field(repr=False, return_type=dict)
    @cached_property
    def _details(self):
        """Carga los detalles desde la URL de detalles si aún no se han cargado."""
        html = _browser_get(self.url, [])
        if _is_cloudflare_challenge(html):
            raise CloudflareChallengeError(
                "Cloudflare requiere una nueva verificación. Ejecutá "
                "`cuitonline --login` y completala antes de pedir detalles."
            )
        soup = Sopita(html, "html.parser")
        title = soup.title.get_text(strip=True) if soup.title else ""
        if "404" in title:
            raise ContentUnavailableError(
                "El sitio no entregó un detalle real para esta sesión. "
                "La búsqueda sigue mostrando una vista restringida."
            )
        return {
            "genero": soup._extract("itemprop", "gender"),
            "direccion": soup._extract("itemprop", "streetAddress"),
            "provincia": soup._extract("itemprop", "addressRegion"),
            "localidad": soup._extract("itemprop", "addressLocality"),
            "nacionalidad": soup._extract("itemprop", "nationality"),
            "monotributo": soup._extract("li:-soup-contains(Monotributista) span"),
            "empleador": soup._extract("li:-soup-contains(Empleador) span") == "Sí",
        }

    @computed_field
    @property
    def dni(self) -> Optional[int]:
        if self.tipo_persona == "física":
            return int(self.cuit.split("-")[1])

    @computed_field
    @property
    def genero(self) -> Optional[str]:
        return self._details.get("genero")

    @computed_field
    @property
    def direccion(self) -> Optional[str]:
        return self._details.get("direccion")

    @computed_field
    @property
    def provincia(self) -> Optional[str]:
        return self._details.get("provincia")

    @computed_field
    @property
    def localidad(self) -> Optional[str]:
        return self._details.get("localidad")

    @computed_field
    @property
    def nacionalidad(self) -> Optional[str]:
        return self._details.get("nacionalidad")

    @computed_field
    @property
    def monotributo(self) -> Optional[str]:
        return self._details.get("monotributo")

    @computed_field
    @property
    def empleador(self) -> Optional[bool]:
        return self._details.get("empleador")

    @computed_field
    @property
    def nombre_pila(self) -> Optional[str]:
        if not self.parse_nombres or self.tipo_persona != "física" or HumanName is None:
            return None
        partes = self.nombre.split(" ", 1)
        formatted = f"{partes[0]}, {partes[1]}" if len(partes) == 2 else self.nombre
        return HumanName(formatted).first or None

    @computed_field
    @property
    def apellido(self) -> Optional[str]:
        if not self.parse_nombres or self.tipo_persona != "física" or HumanName is None:
            return None
        partes = self.nombre.split(" ", 1)
        formatted = f"{partes[0]}, {partes[1]}" if len(partes) == 2 else self.nombre
        return HumanName(formatted).last or None


def _extraer_tipo_persona(item) -> str:
    """Extrae 'física' o 'jurídica' del texto del resultado de búsqueda."""
    facets = item.select_one(".doc-facets")
    if facets:
        for texto in facets.strings:
            t = texto.strip()
            if "Jurídica" in t:
                return "jurídica"
            if "Física" in t:
                return "física"
    return "física"


_FACETA_A_PARAM = {
    "ganancias": "f0[]",
    "iva": "f1[]",
    "monotributo": "f2[]",
    "empleador": "f4[]",
    "persona": "f5[]",
    "nacionalidad": "f6[]",
}


def _parsear_filtros(filtros: Optional[str]) -> list[tuple[str, str]]:
    """Convierte 'persona:juridica,iva:iva_exento' en lista de (fN[], valor).

    Cada faceta tiene su propio parámetro URL según el sitio:
    - ganancias → f0[], iva → f1[], monotributo → f2[]
    - empleador → f4[], persona → f5[], nacionalidad → f6[]
    """
    if not filtros:
        return [("f5[]", "persona:fisica")]
    params = []
    for f in filtros.split(","):
        f = f.strip()
        faceta = f.split(":")[0] if ":" in f else ""
        param = _FACETA_A_PARAM.get(faceta, "f5[]")
        params.append((param, f))
    return params


class Busqueda:
    """Consulta paginada de personas en cuitonline.com."""

    def __init__(
        self,
        criterio: str,
        pagina_inicial: int = 1,
        filtros: Optional[str] = None,
        parse_nombres: bool = False,
    ):
        self.criterio = criterio
        self.pagina_actual = pagina_inicial
        self.filtros = filtros
        self.parse_nombres = parse_nombres
        self.resultados = self._search(criterio, pagina=pagina_inicial)

    def siguiente(self):
        """Avanza a la página siguiente y actualiza los resultados."""
        self.pagina_actual += 1
        self.resultados = self._search(self.criterio, self.pagina_actual)

    def _search(self, q: str, pagina: int = 1) -> List[Persona]:
        return browser_search(
            q,
            pagina=pagina,
            filtros=self.filtros,
            parse_nombres=self.parse_nombres,
        )


def search(
    q: str,
    pagina: int = 1,
    filtros: Optional[str] = None,
    parse_nombres: bool = False,
) -> List[Persona]:
    return Busqueda(
        q, pagina_inicial=pagina, filtros=filtros, parse_nombres=parse_nombres
    ).resultados


def main():
    parser = argparse.ArgumentParser(description="Buscar personas en CUIT Online.")
    parser.add_argument(
        "-v", "--version", action="version", version=f"%(prog)s {__version__}"
    )
    parser.add_argument(
        "criterio", nargs="?", help="Criterio de búsqueda (nombre, cuit, dni, etc.)"
    )
    parser.add_argument(
        "--login",
        action="store_true",
        help="Abrir Chrome para completar y guardar la verificación de Cloudflare",
    )
    parser.add_argument(
        "-p",
        "--pagina",
        type=int,
        default=1,
        help="Número de página a buscar (por defecto: 1)",
    )
    parser.add_argument(
        "-f",
        "--filtros",
        default=None,
        help="Filtros de facetados separados por coma (ej: persona:juridica,iva:iva_exento)",
    )
    parser.add_argument(
        "--nombres",
        action="store_true",
        default=False,
        help="Separar nombre_pila y apellido (requiere: pip install cuitonline[nombres])",
    )
    parser.add_argument(
        "--detalles",
        action="store_true",
        help="Incluir detalles de cada resultado mediante Chrome",
    )
    args = parser.parse_args()

    if args.login:
        try:
            browser_login(args.criterio or "cuit")
        except (BrowserSupportError, CloudflareChallengeError) as error:
            parser.error(str(error))
        return
    if not args.criterio:
        parser.error("criterio es obligatorio salvo al usar --login")

    try:
        resultados = Busqueda(
            args.criterio,
            pagina_inicial=args.pagina,
            filtros=args.filtros,
            parse_nombres=args.nombres,
        ).resultados
        resultado_json = [
            _persona_a_dict(persona, detalles=args.detalles) for persona in resultados
        ]
    except (BrowserSupportError, CloudflareChallengeError, ContentUnavailableError) as error:
        parser.error(str(error))

    print(
        json.dumps(
            resultado_json,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
