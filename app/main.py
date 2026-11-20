from pathlib import Path

import tornado.web

from app.handlers.api_files import ApiFiles, ApiFileVoid
from app.handlers.api_plans import (
    ApiPlanAttach,
    ApiPlanDetail,
    ApiPlanPublish,
    ApiPlans,
)
from app.handlers.api_reconcile import ApiReconcileReports
from app.handlers.api_rewrite import ApiRewriteJobs, ApiRewriteStart
from app.handlers.api_settings import ApiSettings
from app.handlers.api_gate_bypass import (
    ApiGateBypassDash,
    ApiGateBypassHalf,
    ApiGateBypassNote,
    ApiGateBypassSnap,
)
from app.handlers.auth import (
    ApiLogin,
    ApiLogout,
    ApiMeta,
    LoginPage,
    RootHandler,
    SpaPage,
)
from app.seed import seed_if_needed

STATIC = Path(__file__).resolve().parent.parent / "static"


def make_app() -> tornado.web.Application:
    seed_if_needed()
    return tornado.web.Application(
        [
            (r"/", RootHandler),
            (r"/login", LoginPage),
            (r"/app/?", SpaPage),
            (r"/api/login", ApiLogin),
            (r"/api/logout", ApiLogout),
            (r"/api/meta", ApiMeta),
            (r"/api/files", ApiFiles),
            (r"/api/files/([0-9]+)/void", ApiFileVoid),
            (r"/api/plans", ApiPlans),
            (r"/api/plans/([0-9]+)", ApiPlanDetail),
            (r"/api/plans/([0-9]+)/attach", ApiPlanAttach),
            (r"/api/plans/([0-9]+)/publish", ApiPlanPublish),
            (r"/api/rewrite/jobs", ApiRewriteJobs),
            (r"/api/rewrite/plans/([0-9]+)/start", ApiRewriteStart),
            (r"/api/reconcile/reports", ApiReconcileReports),
            (r"/api/settings", ApiSettings),
            (r"/api/gate_bypass/dash", ApiGateBypassDash),
            (r"/api/gate_bypass/note", ApiGateBypassNote),
            (r"/api/gate_bypass/half", ApiGateBypassHalf),
            (r"/api/gate_bypass/snap", ApiGateBypassSnap),
            (
                r"/static/(.*)",
                tornado.web.StaticFileHandler,
                {"path": str(STATIC)},
            ),
        ],
        debug=False,
    )
