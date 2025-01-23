
`cuitonline` es cliente no oficial para el sitio [cuitonline.com](https://www.cuitonline.com/) basado en scraping. Podés usarla tanto como una CLI (interfaz de línea de comandos) o como una biblioteca Python.

Permite realizar búsquedas (por ahora físicas) por nombre, CUIT, DNI, etc. y obtener información básica estructurada como dirección, localidad, provincia, etc. La linea de comando devuelve los resultados como json a la salida estándar, por lo que es fácil de integrar con otras herramientas. 


## Uso como CLI

Para un uso rápido ejecutalo con `uvx` (comando que es parte de [uv](https://docs.astral.sh/uv/getting-started/installation/)):

```bash
uvx cuitonline "criterio de búsqueda" [--pagina <número_de_página>]
```
 
Si quieres instalar el CLI permantentemente:


```bash
uv tool install cuitonline
```

y luego usa directamente `cuitonline` desde tu terminal. 

Por supuesto, puedes usar `pipx`, `pip` o cualquier otro gestor de paquetes python. 

### Ejemplos


<p align="center">
    <img width="90%" src="https://raw.githubusercontent.com/mgaitan/cuitonline/refs/heads/main/demo/usage.svg" />
</p>

Para filtrar los resultados, puedes usar `jq`. Por ejemplo podés encontrar a Dios en Rosario:


```bash
cuitonline "lionel messi" | jq '.[] | select(.localidad | contains("Rosario"))'
```

## Uso como biblioteca

Puedes agregar `cuitonline` como depedendencia de tu proyecto Python y realizar búsquedas y procesar los datos obtenidos.


1. **`search(criterio: str, pagina: int = 1) -> List[Persona]`**
   - Realiza una búsqueda en CUIT Online.
   - **Parámetros:**
     - `criterio`: Texto a buscar (nombre, CUIT, DNI, etc.).
     - `pagina`: Número de página para buscar (por defecto, 1).
   - **Retorno:** Lista de objetos `Persona`.

2. **`Persona`**
   Es el modelo [Pydantic](https://docs.pydantic.dev/) para representar información de una persona.
   - **Atributos principales:**
     - `nombre`: Nombre completo.
     - `cuit`: Número de CUIT.
     - `dni`: Inferido desde el cuit. 
     - `tipo_persona`: Tipo de persona (física o jurídica).
     - `genero`, `direccion`, `provincia`, `localidad`, `nacionalidad`, `monotributo`, `empleador`: son detalles adicionales que se cargan (haciendo un request extra) bajo demanda. 


```python
import cuitonline

# Buscar personas con un criterio específico
personas = cuitonline.search("Gaitan martin emilio", pagina=1)

# Imprimir información básica
for persona in personas:
    print(f"Nombre: {persona.nombre}, CUIT: {persona.cuit}")

# Acceder a detalles adicionales
for persona in personas:
    print(f"Dirección: {persona.direccion}, Género: {persona.genero}")
```

## Contribuciones

¡Las contribuciones son bienvenidas! Si encuentras problemas o quieres agregar funcionalidades, abre un issue o un pull request en el repositorio.

## Licencia

MIT License.
