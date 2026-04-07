"""Stripe Webhook Handler for BIG Hat Sponsor Portal

Handles payment webhook events from Stripe
"""

from fastapi import APIRouter, Request, HTTPException
import os
import logging
from datetime import datetime, timezone
from database import db

from emergentintegrations.payments.stripe.checkout import StripeCheckout

logger = logging.getLogger(__name__)

router = APIRouter(tags=["webhooks"])

STRIPE_API_KEY = os.environ.get("STRIPE_API_KEY", "")


@router.post("/webhook/stripe")
async def stripe_webhook(request: Request):
    """Handle Stripe webhook events"""
    try:
        # Get raw body
        body = await request.body()
        signature = request.headers.get("Stripe-Signature")
        
        if not signature:
            logger.warning("Missing Stripe signature")
            raise HTTPException(status_code=400, detail="Missing Stripe signature")
        
        # Initialize Stripe checkout
        host_url = str(request.base_url).rstrip('/')
        webhook_url = f"{host_url}/api/webhook/stripe"
        stripe_checkout = StripeCheckout(api_key=STRIPE_API_KEY, webhook_url=webhook_url)
        
        # Handle webhook
        webhook_response = await stripe_checkout.handle_webhook(body, signature)
        
        logger.info(f"Received Stripe webhook: {webhook_response.event_type}")
        
        # Process based on event type
        if webhook_response.event_type == "checkout.session.completed":
            session_id = webhook_response.session_id
            payment_status = webhook_response.payment_status
            
            if payment_status == "paid":
                # Update transaction
                await db.payment_transactions.update_one(
                    {"session_id": session_id},
                    {"$set": {
                        "status": "completed",
                        "payment_status": "paid",
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }}
                )
                
                # The subscription activation is handled by the status polling endpoint
                # This is a backup in case the frontend doesn't poll
                logger.info(f"Webhook: Payment completed for session {session_id}")
        
        elif webhook_response.event_type == "checkout.session.expired":
            session_id = webhook_response.session_id
            
            await db.payment_transactions.update_one(
                {"session_id": session_id},
                {"$set": {
                    "status": "expired",
                    "payment_status": "expired",
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }}
            )
            
            logger.info(f"Webhook: Session expired {session_id}")
        
        return {"received": True}
        
    except Exception as e:
        logger.error(f"Webhook error: {str(e)}")
        # Return 200 to acknowledge receipt (Stripe will retry on non-200)
        return {"received": True, "error": str(e)}
