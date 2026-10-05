from fastapi import FastAPI
from .lifecycle import lifespan
from .middleware import account_scope
from .observability import request_telemetry
from ..service_admin_api import router as admin_router
from ..report_preview_api import router as preview_router
from ..submission_api import router as submission_router

app = FastAPI(title="K-ODAME Service API", version="2.4", lifespan=lifespan)
app.middleware("http")(account_scope)
app.middleware("http")(request_telemetry)
app.include_router(admin_router)
app.include_router(preview_router)
app.include_router(submission_router)
from .auth_routes import router as auth_routes
app.include_router(auth_routes)
from .project_routes import router as project_routes
app.include_router(project_routes)
from .intake_routes import router as intake_routes
app.include_router(intake_routes)
from .evaluation_routes import router as evaluation_routes
app.include_router(evaluation_routes)
from .report_routes import router as report_routes
app.include_router(report_routes)
from .operations_routes import router as operations_routes
app.include_router(operations_routes)
from .review_routes import router as review_routes
app.include_router(review_routes)
