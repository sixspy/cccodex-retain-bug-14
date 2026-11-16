import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class Config:
    LAB_NAME = "留存裁撤台"
    LAB_CODE = "cc-retain-lab"
    SECRET = os.environ.get("RETAIN_SECRET", "cc-retain-lab-dev-secret")
    ADMIN_USER = "admin"
    ADMIN_PASSWORD = "123456"
    HOST = os.environ.get("HOST", "127.0.0.1")
    PORT = int(os.environ.get("PORT", "6500"))

    @staticmethod
    def database() -> str:
        return os.environ.get(
            "DATABASE_PATH",
            str(ROOT / "instance" / "retain_lab.db"),
        )
