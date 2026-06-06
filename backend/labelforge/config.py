from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # When DISABLE_AUTH=true the app runs with no app-level auth (intended for
    # deployments fronted by a reverse proxy that handles auth, e.g. Traefik).
    # Default is secure: auth on, and the app refuses to start without a token.
    disable_auth: bool = False
    api_token: str = ""
    printer_host: str
    printer_model: str = "QL-820NWB"
    # one of: network, linux_kernel, pyusb
    printer_backend: str = "network"
    data_dir: Path = Path("/data")
    default_label_media: str = "62"
    log_level: str = "INFO"
    catalog_auto_merge: bool = True

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @model_validator(mode="after")
    def _require_token_unless_disabled(self) -> "Settings":
        if not self.disable_auth and not self.api_token:
            raise ValueError(
                "API_TOKEN is required (set DISABLE_AUTH=true to run without app-level auth)"
            )
        return self


settings = Settings()
