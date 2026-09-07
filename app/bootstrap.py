"""Application assembly. `create_app()` is the single place BEACN is put together."""

from __future__ import annotations

from sillo import SilloApp
from sillo.auth import AuthenticationMiddleware
from sillo.auth.session_auth import SessionAuthBackend
from sillo.record import setup_record
from sillo.security import CorsConfig, CORSMiddleware
from sillo.security.csrf import CSRFConfig, CSRFMiddleware
from sillo.session import SessionConfig, SessionMiddleware

from app.config import check_production, config, cors_origins
from app.inertia import BUILD_DIR, build_inertia, share_globals
from database.models import User

__all__ = ["create_app"]


def create_app() -> SilloApp:
    from routes.web import routes as web_routes

    warnings = check_production()
    if warnings:
        raise RuntimeError(
            "Refusing to start in production with unsafe configuration:\n  - "
            + "\n  - ".join(warnings)
        )

    application = SilloApp(
        debug=config.debug,
        title=config.app_name,
        version="0.1.0",
        routes=list(web_routes),
    )

    _register_middleware(application)
    _register_database(application)
    _register_work(application)
    _register_realtime(application)
    _register_static(application)
    _register_routers(application)
    _register_observability(application)
    _register_bootstrap_hooks(application)
    return application


def _register_middleware(application: SilloApp) -> None:
    inertia = build_inertia()
    share_globals(inertia)
    inertia.middleware(application)
    application.state["inertia"] = inertia

    application.use(
        AuthenticationMiddleware(user_model=User, backend=SessionAuthBackend())
    )
    application.use(
        CSRFMiddleware(
            config=CSRFConfig(
                enabled=True,
                cookie_name="XSRF-TOKEN",
                header_name="X-XSRF-TOKEN",
                cookie_httponly=False,
                cookie_secure=config.cookie_secure,
                secret_key=config.secret_key,
                # The API and the realtime endpoints authenticate on the
                # Authorization header alone and ignore cookies, so there is no
                # ambient credential for a forged request to ride on.
                exempt_urls=[r"^/api/.*", r"^/realtime$", r"^/metrics$", r"^/health$"],
            )
        )
    )
    application.use(
        SessionMiddleware(
            config=SessionConfig(
                session_cookie_name=config.session_cookie_name,
                session_expiration_time=config.session_lifetime,
                session_cookie_secure=config.cookie_secure,
            ),
            secret_key=config.secret_key,
        )
    )
    application.use(
        CORSMiddleware(
            config=CorsConfig(allow_origins=cors_origins(), allow_credentials=True)
        )
    )


def _register_database(application: SilloApp) -> None:
    from database.config import MIGRATIONS_MODULE, MODEL_MODULES, database_config

    manager = setup_record(application, database_config(), model_modules=MODEL_MODULES)
    manager.set_migrations(MIGRATIONS_MODULE)


def _register_work(application: SilloApp) -> None:
    from sillo.work import setup_work

    setup_work(application)

    async def _bind_queue() -> None:
        from app.queue import bind_jobs

        bind_jobs()

    application.on_startup(_bind_queue)


def _register_realtime(application: SilloApp) -> None:
    from realtime import setup as setup_realtime
    from routes.api.realtime import register as register_realtime_routes

    setup_realtime(application)
    register_realtime_routes(application)


def _register_static(application: SilloApp) -> None:
    from sillo.core.routing import Group
    from sillo.static import StaticFiles

    assets = BUILD_DIR / "assets"
    if assets.is_dir():
        application.add_route(Group(path="/assets", app=StaticFiles(directory=str(assets))))
    from app.config import BASE_DIR

    pub_dir = BASE_DIR / "public"
    if pub_dir.is_dir():
        application.add_route(Group(path="/static", app=StaticFiles(directory=str(pub_dir))))


def _register_routers(application: SilloApp) -> None:
    from routes.api.control import router as control_router
    from routes.api.v1 import router as v1_router

    application.mount_router(v1_router)
    application.mount_router(control_router)


def _register_observability(application: SilloApp) -> None:
    from sillo.core.routing import Route

    from observability.metrics import metrics_endpoint
    from routes.api.control import health as health_endpoint

    application.add_route(Route("/metrics", handler=metrics_endpoint, methods=["GET"], name="metrics"))
    application.add_route(Route("/health", handler=health_endpoint, methods=["GET"], name="health"))


def _register_bootstrap_hooks(application: SilloApp) -> None:
    async def _ensure_roles() -> None:
        from app.authz import ensure_roles

        await ensure_roles()

    application.on_startup(_ensure_roles)
