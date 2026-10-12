from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from .admin_page import ADMIN_HTML
from .api import admin, webfiles
from .config import HOST, ADMIN_PORT


def build_app() -> FastAPI:
    app = FastAPI(title="SFTP Admin Server", docs_url="/api/docs")
    app.include_router(admin.router)
    app.include_router(webfiles.router)

    @app.get("/")
    def root():
        return {"service": "sftpserver",
                "admin": f"http://{HOST}:{ADMIN_PORT}/admin",
                "docs": f"http://{HOST}:{ADMIN_PORT}/api/docs"}

    @app.get("/admin", response_class=HTMLResponse)
    def admin_ui():
        return ADMIN_HTML

    return app
