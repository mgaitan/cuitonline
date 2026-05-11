[![PyPI version](https://img.shields.io/pypi/v/cuitonline.svg)](https://pypi.org/project/cuitonline/)

`cuitonline` es un cliente no oficial para el sitio [cuitonline.com](https://www.cuitonline.com/) basado en scraping. Podés usarlo tanto como CLI (interfaz de línea de comandos) o como biblioteca Python.

Permite realizar búsquedas de personas (físicas y jurídicas) por nombre, CUIT, DNI, etc. y obtener información básica estructurada como dirección, localidad, provincia, etc. La línea de comando devuelve los resultados como JSON a la salida estándar, por lo que es fácil de integrar con otras herramientas.


## Uso como CLI

Para un uso rápido ejecutalo con `uvx` (que forma parte de [uv](https://docs.astral.sh/uv/getting-started/installation/)):

```bash
uvx cuitonline "criterio de búsqueda" [--pagina <número>] [--filtros <faceta:valor,...>]
```

Si querés instalarlo permanentemente:

```bash
uv tool install cuitonline
```

y después usá directamente `cuitonline` desde tu terminal.

También podés usar `pipx`, `pip` o cualquier otro gestor de paquetes Python.

### Ejemplos

<p align="center">
    <img width="90%" src="https://raw.githubusercontent.com/mgaitan/cuitonline/refs/heads/main/demo/usage.svg" />
</p>

Para filtrar los resultados podés usar `jq`. Por ejemplo, encontrá a Messi en Rosario:

```bash
cuitonline "lionel messi" | jq '.[] | select(.localidad | contains("Rosario"))'
```

#### Filtros de facetados

El sitio ofrece filtros para acotar los resultados. Pasalos con `-f` separados por coma:

```bash
# Solo personas jurídicas
cuitonline "gaitan" -f persona:juridica

# Personas físicas exentas de IVA
cuitonline "gaitan" -f persona:fisica,iva:iva_exento

# Monotributistas de Argentina
cuitonline "gaitan" -f monotributo:inscripto,nacionalidad:argentina
```

Los filtros disponibles y sus valores son:

| Faceta        | Parámetro | Valores posibles                                          |
|---------------|-----------|-----------------------------------------------------------|
| `persona`     | f5        | `fisica`, `juridica`                                      |
| `iva`         | f1        | `iva_inscripto`, `iva_exento`, `no_inscripto`, `iva_no_alcanzado` |
| `monotributo` | f2        | `inscripto`, `no_inscripto`                               |
| `empleador`   | f4        | `si`, `no`                                                |
| `nacionalidad`| f6        | `argentina`, `inmigrante`                                 |

#### Paginación

```bash
cuitonline "gaitan" --pagina 2
```


## Uso como biblioteca

Agregá `cuitonline` como dependencia de tu proyecto Python (por ejemplo con `uv add cuitonline`)  y realizá búsquedas procesando los datos obtenidos.

### `search(criterio, pagina=1, filtros=None) → List[Persona]`

```python
import cuitonline

# Búsqueda básica
personas = cuitonline.search("Gaitan martin emilio")

for persona in personas:
    print(f"Nombre: {persona.nombre}, CUIT: {persona.cuit}")

# Con filtros
juridicas = cuitonline.search("gaitan", filtros="persona:juridica")

# Acceder a detalles adicionales (hace un request extra por persona)
for persona in personas:
    print(f"Dirección: {persona.direccion}, Género: {persona.genero}")
```

### `Busqueda` — consultas paginadas

```python
import cuitonline

b = cuitonline.Busqueda("gaitan martin", filtros="iva:iva_inscripto")

print(b.resultados)   # página 1
b.siguiente()
print(b.resultados)   # página 2
```

### `Persona` — modelo de datos

Modelo [Pydantic](https://docs.pydantic.dev/) que representa a una persona:

| Campo          | Tipo            | Descripción                                                  |
|----------------|-----------------|--------------------------------------------------------------|
| `nombre`       | `str`           | Nombre completo tal como lo devuelve el sitio                |
| `nombre_pila`  | `str \| None`   | Primer nombre (solo personas físicas, via nameparser)        |
| `apellido`     | `str \| None`   | Apellido (solo personas físicas, via nameparser)             |
| `cuit`         | `str`           | Número de CUIT/CUIL                                          |
| `dni`          | `int \| None`   | Inferido desde el CUIT (solo personas físicas)               |
| `tipo_persona` | `str`           | `"física"` o `"jurídica"`                                   |
| `genero`       | `str \| None`   | Género (requiere request extra)                              |
| `direccion`    | `str \| None`   | Dirección (requiere request extra)                           |
| `provincia`    | `str \| None`   | Provincia (requiere request extra)                           |
| `localidad`    | `str \| None`   | Localidad (requiere request extra)                           |
| `nacionalidad` | `str \| None`   | Nacionalidad (requiere request extra)                        |
| `monotributo`  | `str \| None`   | Categoría de monotributo (requiere request extra)            |
| `empleador`    | `bool \| None`  | Si es empleador (requiere request extra)                     |


## Desarrollo y tests

Cloná el repo e instalá las dependencias de desarrollo con [uv](https://docs.astral.sh/uv/):

```bash
git clone https://github.com/mgaitan/cuitonline
cd cuitonline
uv sync --group dev
```

### Correr los tests

Por defecto los tests usan cassettes VCR grabados (sin red):

```bash
uv run pytest
```

Para correr contra el sitio real (requiere internet):

```bash
uv run pytest --disable-recording
```

Para re-grabar los cassettes (útil si el sitio cambia su HTML):

```bash
uv run pytest --record-mode=all
```

## Contribuciones

¡Las contribuciones son bienvenidas! Si encontrás problemas o querés agregar funcionalidades, abrí un issue o un pull request en el repositorio.

## Licencia

MIT License.
