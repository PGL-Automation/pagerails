from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parent.parent / ".env",
        extra="ignore",
    )

    recon_db_path: str = "../pcg_recon/recon.db"
    recon_inputs_dir: str = "../pcg_recon/samples/inputs"
    recon_config_dir: str = "../pcg_recon/config"
    recon_outputs_dir: str = "../pcg_recon/samples/output"
    upload_dir: str = "./uploads"

    jwt_secret: str = "dev-secret-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 480

    cors_origins: str = "http://localhost:3000"
    frontend_url: str = "https://recon.pagecapital.ng"  # FRONTEND_URL

    # Default admin user — created on first boot if no users exist in the DB
    admin_email: str = "admin@pagerails.app"
    admin_password: str = "changeme"  # must be changed after first login

    def db_path(self) -> Path:
        p = Path(self.recon_db_path)
        return p if p.is_absolute() else (Path(__file__).parent.parent / p).resolve()

    def inputs_dir(self) -> Path:
        p = Path(self.recon_inputs_dir)
        return p if p.is_absolute() else (Path(__file__).parent.parent / p).resolve()

    def config_dir(self) -> Path:
        p = Path(self.recon_config_dir)
        return p if p.is_absolute() else (Path(__file__).parent.parent / p).resolve()

    def outputs_dir(self) -> Path:
        p = Path(self.recon_outputs_dir)
        return p if p.is_absolute() else (Path(__file__).parent.parent / p).resolve()

    def uploads_dir(self) -> Path:
        p = Path(self.upload_dir)
        d = p if p.is_absolute() else (Path(__file__).parent.parent / p).resolve()
        d.mkdir(parents=True, exist_ok=True)
        return d

    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",")]


settings = Settings()
