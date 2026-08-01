"""Stripe Checkout + webhook + Customer Portal."""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

import stripe
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from . import db
from .auth_service import require_user
from .membership import is_vip_user
from . import settings

logger = logging.getLogger(__name__)
router = APIRouter(tags=["billing"])


def _stripe_ready() -> None:
    settings.refresh_from_env()
    if not (settings.STRIPE_SECRET_KEY and settings.STRIPE_PRICE_ID):
        raise HTTPException(
            status_code=503,
            detail="未配置 Stripe（需要 STRIPE_SECRET_KEY 与 STRIPE_PRICE_ID）。",
        )
    stripe.api_key = settings.STRIPE_SECRET_KEY


def _resolve_user_id_from_subscription(sub: Dict[str, Any]) -> Optional[int]:
    meta = sub.get("metadata") or {}
    raw = meta.get("user_id")
    if raw:
        try:
            return int(raw)
        except (TypeError, ValueError):
            pass
    customer_id = sub.get("customer")
    if isinstance(customer_id, dict):
        customer_id = customer_id.get("id")
    if customer_id:
        user = db.get_user_by_stripe_customer(str(customer_id))
        if user:
            return int(user["id"])
    return None


def _period_end_from_subscription(sub: Dict[str, Any]) -> float:
    """Support classic Subscription.current_period_end and newer item-level fields."""
    raw = sub.get("current_period_end")
    if raw:
        return float(raw)
    items = sub.get("items") or {}
    data = items.get("data") if isinstance(items, dict) else None
    if data:
        for item in data:
            if isinstance(item, dict) and item.get("current_period_end"):
                return float(item["current_period_end"])
    return 0.0


def _sync_subscription_object(sub_obj: Any, user_id: Optional[int] = None) -> None:
    if hasattr(sub_obj, "to_dict"):
        sub = sub_obj.to_dict()
    elif isinstance(sub_obj, dict):
        sub = sub_obj
    else:
        sub = dict(sub_obj)

    uid = user_id or _resolve_user_id_from_subscription(sub)
    if not uid:
        logger.warning("subscription sync skipped: no user_id for %s", sub.get("id"))
        return

    customer_id = sub.get("customer")
    if isinstance(customer_id, dict):
        customer_id = customer_id.get("id")
    if customer_id:
        db.set_stripe_customer_id(uid, str(customer_id))

    db.upsert_subscription(
        user_id=uid,
        stripe_subscription_id=str(sub["id"]),
        status=str(sub.get("status") or "incomplete"),
        current_period_end=_period_end_from_subscription(sub),
        cancel_at_period_end=bool(sub.get("cancel_at_period_end")),
    )


def _ensure_customer(user: Dict[str, Any]) -> str:
    existing = user.get("stripe_customer_id")
    if existing:
        return str(existing)
    try:
        customer = stripe.Customer.create(
            email=user["email"],
            metadata={"user_id": str(user["id"])},
        )
    except stripe.AuthenticationError as exc:
        logger.exception("stripe auth failed while creating customer")
        raise HTTPException(
            status_code=502,
            detail="Stripe 密钥无效，请检查 backend/.env 的 STRIPE_SECRET_KEY（需 sk_test_...）。",
        ) from exc
    except stripe.StripeError as exc:
        logger.exception("stripe customer create failed")
        raise HTTPException(
            status_code=502,
            detail="创建支付客户失败：{}".format(exc.user_message or str(exc)),
        ) from exc
    db.set_stripe_customer_id(int(user["id"]), customer.id)
    return customer.id


@router.post("/api/billing/checkout")
def create_checkout(request: Request):
    _stripe_ready()
    user = require_user(request)
    user_id = int(user["id"])

    if is_vip_user(user_id):
        raise HTTPException(
            status_code=400,
            detail="你已是 Pro 会员。如需管理订阅，请使用「管理订阅」。",
        )

    try:
        customer_id = _ensure_customer(user)
        minute_bucket = int(time.time() // 60)
        idempotency_key = "checkout:{}:{}:{}".format(
            user_id, settings.STRIPE_PRICE_ID, minute_bucket
        )
        session = stripe.checkout.Session.create(
            mode="subscription",
            customer=customer_id,
            client_reference_id=str(user_id),
            metadata={"user_id": str(user_id)},
            line_items=[{"price": settings.STRIPE_PRICE_ID, "quantity": 1}],
            success_url=settings.PUBLIC_APP_URL + "/?billing=success",
            cancel_url=settings.PUBLIC_APP_URL + "/?billing=cancel",
            subscription_data={"metadata": {"user_id": str(user_id)}},
            allow_promotion_codes=True,
            idempotency_key=idempotency_key,
        )
    except HTTPException:
        raise
    except stripe.StripeError as exc:
        logger.exception("checkout create failed")
        raise HTTPException(
            status_code=502,
            detail="创建支付会话失败：{}".format(exc.user_message or str(exc)),
        ) from exc

    if not session.url:
        raise HTTPException(status_code=502, detail="Stripe 未返回支付链接")
    return {"url": session.url}


@router.post("/api/billing/portal")
def create_portal(request: Request):
    _stripe_ready()
    user = require_user(request)
    customer_id = user.get("stripe_customer_id")
    if not customer_id:
        raise HTTPException(status_code=400, detail="尚未开通订阅，请先升级 Pro")

    try:
        session = stripe.billing_portal.Session.create(
            customer=str(customer_id),
            return_url=settings.PUBLIC_APP_URL + "/?billing=portal",
        )
    except stripe.StripeError as exc:
        logger.exception("portal create failed")
        raise HTTPException(
            status_code=502,
            detail="打开订阅管理失败：{}".format(exc.user_message or str(exc)),
        ) from exc

    return {"url": session.url}


@router.post("/api/billing/webhook")
async def stripe_webhook(request: Request):
    settings.refresh_from_env()
    if not settings.STRIPE_SECRET_KEY:
        return JSONResponse(status_code=503, content={"detail": "Stripe 未配置"})
    stripe.api_key = settings.STRIPE_SECRET_KEY

    payload = await request.body()
    sig = request.headers.get("stripe-signature")
    if not settings.STRIPE_WEBHOOK_SECRET:
        return JSONResponse(status_code=503, content={"detail": "未配置 STRIPE_WEBHOOK_SECRET"})
    if not sig:
        return JSONResponse(status_code=400, content={"detail": "缺少 stripe-signature"})

    try:
        event = stripe.Webhook.construct_event(
            payload, sig, settings.STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        return JSONResponse(status_code=400, content={"detail": "Invalid payload"})
    except stripe.SignatureVerificationError:
        return JSONResponse(status_code=400, content={"detail": "Invalid signature"})

    event_id = event["id"]
    event_type = event["type"]
    if not db.try_claim_stripe_event(event_id, event_type):
        return {"received": True, "duplicate": True}

    data_object = event["data"]["object"]

    try:
        if event_type == "checkout.session.completed":
            _handle_checkout_completed(data_object)
        elif event_type in (
            "customer.subscription.created",
            "customer.subscription.updated",
        ):
            _sync_subscription_object(data_object)
        elif event_type == "customer.subscription.deleted":
            _handle_subscription_deleted(data_object)
        elif event_type == "invoice.payment_failed":
            _handle_invoice_payment_failed(data_object)
        else:
            logger.info("ignored stripe event %s", event_type)
    except Exception:
        logger.exception("failed processing stripe event %s", event_id)
        # Allow Stripe to retry: remove claim so next delivery reprocesses
        with db.get_conn() as conn:
            conn.execute("DELETE FROM stripe_events WHERE event_id = ?", (event_id,))
        return JSONResponse(status_code=500, content={"detail": "handler error"})

    return {"received": True}


def _handle_checkout_completed(session: Dict[str, Any]) -> None:
    user_id = None
    raw = session.get("client_reference_id") or (session.get("metadata") or {}).get("user_id")
    if raw:
        try:
            user_id = int(raw)
        except (TypeError, ValueError):
            user_id = None

    customer_id = session.get("customer")
    if isinstance(customer_id, dict):
        customer_id = customer_id.get("id")
    if user_id and customer_id:
        db.set_stripe_customer_id(user_id, str(customer_id))

    sub_id = session.get("subscription")
    if isinstance(sub_id, dict):
        sub_id = sub_id.get("id")
    if not sub_id:
        return

    sub = stripe.Subscription.retrieve(str(sub_id))
    _sync_subscription_object(sub, user_id=user_id)


def _handle_subscription_deleted(sub: Dict[str, Any]) -> None:
    sub_id = str(sub.get("id") or "")
    if not sub_id:
        return
    uid = _resolve_user_id_from_subscription(sub)
    if uid:
        db.upsert_subscription(
            user_id=uid,
            stripe_subscription_id=sub_id,
            status="canceled",
            current_period_end=float(sub.get("current_period_end") or 0),
            cancel_at_period_end=bool(sub.get("cancel_at_period_end")),
        )
    else:
        db.mark_subscription_status(sub_id, "canceled")


def _handle_invoice_payment_failed(invoice: Dict[str, Any]) -> None:
    sub_id = invoice.get("subscription")
    if isinstance(sub_id, dict):
        sub_id = sub_id.get("id")
    if not sub_id:
        return
    try:
        sub = stripe.Subscription.retrieve(str(sub_id))
        _sync_subscription_object(sub)
    except stripe.StripeError:
        db.mark_subscription_status(str(sub_id), "past_due")
