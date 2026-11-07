import pathlib

import custom_components  # vom Test-Plugin bereitgestelltes Paket

_repo = str(pathlib.Path(__file__).resolve().parents[1] / "custom_components")
if _repo not in custom_components.__path__:
    custom_components.__path__.insert(0, _repo)

pytest_plugins = ["pytest_homeassistant_custom_component"]
