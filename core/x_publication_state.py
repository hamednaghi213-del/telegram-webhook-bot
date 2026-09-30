"""Write-ahead guard for X's non-idempotent create-post API.

Uses the existing publication_delivery_parts table and unique delivery/part key.
A marker is removed only after a definite rejection. A lost response, crash, or
failed success persistence leaves it in place for operator reconciliation.
"""
from uuid import uuid4

from core.x_publisher import publish_x

INTENT_PART = "x-send-intent"


def execute_x_delivery(store, source_key, identity, target, text, files):
    state = store.get_delivery(source_key, identity)
    owner = uuid4().hex

    def before_send():
        if getattr(state, "_x_send_pending", False):
            return False
        if state.persistent_delivery_id is not None:
            from core.database import service_supabase
            if service_supabase is None:
                raise RuntimeError("X publication persistence unavailable")
            result = service_supabase.table("publication_delivery_parts").upsert({
                "delivery_id": state.persistent_delivery_id,
                "part_key": INTENT_PART,
                "status": "sending",
                "lease_owner": owner,
                "last_error": "X create-post outcome requires reconciliation until success is recorded",
            }, on_conflict="delivery_id,part_key", ignore_duplicates=True).execute()
            if not any(row.get("lease_owner") == owner for row in (result.data or [])):
                return False
        state._x_send_pending = True
        return True

    def release_send():
        if state.persistent_delivery_id is not None:
            from core.database import service_supabase
            service_supabase.table("publication_delivery_parts").delete().eq(
                "delivery_id", state.persistent_delivery_id
            ).eq("part_key", INTENT_PART).eq("lease_owner", owner).execute()
        state._x_send_pending = False

    return publish_x(target, text, files, before_send, release_send)
