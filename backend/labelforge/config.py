from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    api_token: str
    printer_host: str
    printer_model: str = "QL-820NWB"
    # one of: network, linux_kernel, pyusb
    printer_backend: str = "network"
    data_dir: Path = Path("/var/docker/labelforge")
    default_label_media: str = "62"
    log_level: str = "INFO"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
