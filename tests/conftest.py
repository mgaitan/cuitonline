import pytest


@pytest.fixture
def persona_fisica_data():
    return {
        "nombre": "GAITAN MARTIN EMILIO",
        "cuit": "20-22293909-8",
        "tipo_persona": "física",
        "url": "https://www.cuitonline.com/persona/gaitan/123",
    }


@pytest.fixture
def persona_juridica_data():
    return {
        "nombre": "EMPRESA SA",
        "cuit": "30-12345678-9",
        "tipo_persona": "jurídica",
        "url": "https://www.cuitonline.com/persona/empresa/456",
    }
