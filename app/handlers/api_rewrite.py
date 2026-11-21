from app.handlers.base import BaseHandler
from app.services import merge_gate
from app.services import rewrite as rewrite_svc
from app.services.errors import ServiceError


class ApiRewriteJobs(BaseHandler):
    def get(self):
        self.require_user()
        self.json({"items": rewrite_svc.list_jobs()})


class ApiRewriteStart(BaseHandler):
    def post(self, plan_id: str):
        self.require_user()
        self.json({"job": rewrite_svc.start_rewrite(int(plan_id))})


class ApiPlanGate(BaseHandler):
    """计划闸检摘要：计划屏、合并屏、清单屏都读这一份凭证。"""

    def get(self, plan_id: str):
        self.require_user()
        pid = int(plan_id)
        try:
            summary = merge_gate.summarize(pid)
        except ServiceError:
            raise
        self.json(
            {
                "gate": summary,
                "rejections": merge_gate.list_rejections(pid),
            }
        )
