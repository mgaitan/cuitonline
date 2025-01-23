"""
CLI y biblioteca Python de cuitonline.com. No oficial.
"""

import argparse
import json
from functools import cached_property, partial
from typing import List, Optional

import requests
from bs4 import BeautifulSoup
from pydantic import BaseModel, computed_field
from pydantic_core import to_jsonable_python

base_url = "https://www.cuitonline.com"

__version__ = "0.1.1"


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

    @computed_field(repr=False, return_type=dict)
    @cached_property
    def _details(self):
        """Carga los detalles desde la URL de detalles si aún no se han cargado."""
        response = requests.get(self.url)
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


def search(q: str, pagina: int = 1) -> List[Persona]:
    params = {"q": q, "f5[]": "persona:fisica", "pn": pagina}

    response = requests.get(f"{base_url}/search.php", params=params)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    resultados = []
    for item in soup.select(".hit"):
        persona = Persona(
            nombre=item.select_one(".denominacion h2").get_text(strip=True),
            cuit=item.select_one(".linea-cuit-persona .cuit").get_text(strip=True),
            tipo_persona="física",
            url=f"{base_url}/{item.select_one('.denominacion a')['href']}",
        )
        resultados.append(persona)
    return resultados


def main():
    parser = argparse.ArgumentParser(description="Buscar personas en CUIT Online.")
    parser.add_argument("criterio", help="Criterio de búsqueda (nombre, cuit, dni, etc")
    parser.add_argument(
        "-p",
        "--pagina",
        type=int,
        default=1,
        help="Número de página a buscar (por defecto: 1)",
    )
    args = parser.parse_args()

    personas = search(args.criterio, pagina=args.pagina)

    print(
        json.dumps(
            personas,
            default=partial(to_jsonable_python, exclude=("_details",)),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
