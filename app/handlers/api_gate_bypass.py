from app.handlers.base import BaseHandler
from app.services.gate_bypass_ledger import append_ledger, dashboard
from app.services.gate_bypass_surface import reconcile_surface, snapshot


class ApiGateBypassDash(BaseHandler):
    def get(self):
        self.require_user()
        raw = self.get_argument("plan_id", default="")
        plan_id = int(raw) if raw.isdigit() else None
        self.json(dashboard(plan_id=plan_id))


class ApiGateBypassNote(BaseHandler):
    def post(self):
        self.require_user()
        body = self.read_json()
        self.json(
            append_ledger(
                int(body.get("plan_id") or 0),
                str(body.get("note") or "闸检绕过"),
            )
        )


class ApiGateBypassHalf(BaseHandler):
    def post(self):
        self.require_user()
        self.json(reconcile_surface())


class ApiGateBypassSnap(BaseHandler):
    def get(self):
        self.require_user()
        self.json(snapshot())
