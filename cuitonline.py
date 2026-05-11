"""
CLI y biblioteca Python de cuitonline.com. No oficial.
"""

import argparse
import json
from functools import cached_property, partial
from typing import List, Optional

import requests
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field, computed_field
from pydantic_core import to_jsonable_python

try:
    from nameparser import HumanName
except ImportError:
    HumanName = None

base_url = "https://www.cuitonline.com"

__version__ = "0.1.1"

_headers = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0",
    "Accept-Language": "es-AR,es;q=0.9",
}


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
        response = requests.get(self.url, headers=_headers)
        response.raise_for_status()

        soup = Sopita(response.text, "html.parser")
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
        params = [("q", q), ("pn", str(pagina))] + _parsear_filtros(self.filtros)
        response = requests.get(
            f"{base_url}/search.php", params=params, headers=_headers
        )
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        resultados = []
        for item in soup.select(".hit"):
            cuit = item.select_one(".linea-cuit-persona .cuit").get_text(strip=True)
            persona = Persona(
                nombre=item.select_one(".denominacion h2").get_text(strip=True),
                cuit=cuit,
                tipo_persona=_extraer_tipo_persona(item),
                url=f"{base_url}/{item.select_one('.denominacion a')['href']}",
                parse_nombres=self.parse_nombres,
            )
            resultados.append(persona)
        return resultados


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
        "criterio", help="Criterio de búsqueda (nombre, cuit, dni, etc.)"
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
    args = parser.parse_args()

    resultados = Busqueda(
        args.criterio,
        pagina_inicial=args.pagina,
        filtros=args.filtros,
        parse_nombres=args.nombres,
    )

    print(
        json.dumps(
            resultados.resultados,
            default=partial(to_jsonable_python, exclude=("_details",)),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
