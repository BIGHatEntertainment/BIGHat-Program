"""
Account Deletion Flow for BIG Hat Sponsor Portal
- User initiates deletion request
- Email sent with confirmation link
- User confirms via email link
- Stripe subscription cancelled
- Account deleted
"""
import os
import uuid
import asyncio
import logging
import resend
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, EmailStr
from dotenv import load_dotenv
from database import db

load_dotenv()

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/account-deletion", tags=["account-deletion"])

# Resend configuration
RESEND_API_KEY = os.environ.get("RESEND_API_KEY")
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "onboarding@resend.dev")

if RESEND_API_KEY:
    resend.api_key = RESEND_API_KEY


class DeletionRequest(BaseModel):
    email: EmailStr


class DeletionConfirmRequest(BaseModel):
    token: str


@router.post("/request")
async def request_account_deletion(request: Request, data: DeletionRequest):
    """
    Initiate account deletion - sends confirmation email to user.
    The account is NOT deleted until they confirm via the email link.
    """
    email = data.email.lower()
    
    # Verify account exists
    account = await db.registered_accounts.find_one(
        {"email": email},
        {"_id": 0}
    )
    
    if not account:
        # Don't reveal if account exists or not for security
        return {
            "success": True,
            "message": "If an account exists with this email, a confirmation link has been sent."
        }
    
    # Generate unique deletion token
    deletion_token = f"del_{uuid.uuid4().hex}"
    expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
    
    # Store deletion request
    deletion_record = {
        "id": f"deletion_{uuid.uuid4().hex[:12]}",
        "email": email,
        "token": deletion_token,
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": expires_at.isoformat(),
        "confirmed_at": None,
        "completed_at": None
    }
    
    # Remove any existing pending deletion requests for this email
    await db.deletion_requests.delete_many({"email": email, "status": "pending"})
    
    # Insert new deletion request
    await db.deletion_requests.insert_one(deletion_record)
    
    # Build confirmation URL
    origin = request.headers.get("origin", "https://sponsor.bighat.live")
    confirm_url = f"{origin}/confirm-deletion?token={deletion_token}"
    
    # Send confirmation email
    if RESEND_API_KEY:
        try:
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <title>Confirm Account Deletion</title>
            </head>
            <body style="font-family: Arial, sans-serif; background-color: #1a1a2e; color: #ffffff; padding: 40px;">
                <div style="max-width: 600px; margin: 0 auto; background-color: #16213e; border-radius: 16px; padding: 40px;">
                    <div style="text-align: center; margin-bottom: 30px;">
                        <h1 style="color: #f4d03f; margin: 0;">BIG Hat Entertainment</h1>
                        <p style="color: #ffffff99; margin-top: 8px;">Sponsor Portal</p>
                    </div>
                    
                    <h2 style="color: #ef4444; margin-bottom: 20px;">Account Deletion Request</h2>
                    
                    <p style="color: #ffffffcc; line-height: 1.6;">
                        We received a request to delete your sponsor account associated with <strong>{email}</strong>.
                    </p>
                    
                    <p style="color: #ffffffcc; line-height: 1.6;">
                        <strong>Warning:</strong> This action is permanent and cannot be undone. If you have an active subscription, it will be cancelled and you will not be charged again.
                    </p>
                    
                    <p style="color: #ffffffcc; line-height: 1.6;">
                        If you did not request this, please ignore this email. Your account will remain active.
                    </p>
                    
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{confirm_url}" 
                           style="display: inline-block; background-color: #ef4444; color: #ffffff; text-decoration: none; padding: 14px 28px; border-radius: 8px; font-weight: bold;">
                            Confirm Account Deletion
                        </a>
                    </div>
                    
                    <p style="color: #ffffff66; font-size: 14px; text-align: center;">
                        This link expires in 24 hours.
                    </p>
                    
                    <hr style="border: none; border-top: 1px solid #ffffff20; margin: 30px 0;">
                    
                    <p style="color: #ffffff66; font-size: 12px; text-align: center;">
                        BIG Hat Entertainment - Sponsor Portal<br>
                        This is an automated message. Please do not reply.
                    </p>
                </div>
            </body>
            </html>
            """
            
            params = {
                "from": SENDER_EMAIL,
                "to": [email],
                "subject": "Confirm Account Deletion - BIG Hat Sponsor Portal",
                "html": html_content
            }
            
            # Send email asynchronously
            await asyncio.to_thread(resend.Emails.send, params)
            logger.info(f"Deletion confirmation email sent to {email}")
            
        except Exception as e:
            logger.error(f"Failed to send deletion email: {str(e)}")
            # Don't fail the request - still create the deletion record
            # Admin can manually process if email fails
    else:
        logger.warning("RESEND_API_KEY not configured - deletion email not sent")
    
    return {
        "success": True,
        "message": "A confirmation email has been sent. Please check your inbox and click the link to confirm account deletion."
    }


@router.post("/confirm")
async def confirm_account_deletion(data: DeletionConfirmRequest):
    """
    Confirm and execute account deletion after user clicks email link.
    - Cancels any active Stripe subscription
    - Deletes user data from all collections
    """
    import stripe
    
    # Find the deletion request
    deletion = await db.deletion_requests.find_one(
        {"token": data.token, "status": "pending"},
        {"_id": 0}
    )
    
    if not deletion:
        raise HTTPException(status_code=400, detail="Invalid or expired deletion link")
    
    # Check if expired
    expires_at = datetime.fromisoformat(deletion["expires_at"].replace("Z", "+00:00"))
    if datetime.now(timezone.utc) > expires_at:
        await db.deletion_requests.update_one(
            {"token": data.token},
            {"$set": {"status": "expired"}}
        )
        raise HTTPException(status_code=400, detail="This deletion link has expired. Please request a new one.")
    
    email = deletion["email"]
    
    try:
        # 1. Cancel Stripe subscription if exists
        stripe_api_key = os.environ.get("STRIPE_API_KEY")
        if stripe_api_key:
            stripe.api_key = stripe_api_key
            
            # Find active subscription
            subscription = await db.user_subscriptions.find_one(
                {"user_email": email, "status": "active"},
                {"_id": 0}
            )
            
            if subscription and subscription.get("stripe_subscription_id"):
                try:
                    stripe.Subscription.cancel(subscription["stripe_subscription_id"])
                    logger.info(f"Cancelled Stripe subscription for {email}")
                except stripe.error.StripeError as e:
                    logger.error(f"Failed to cancel Stripe subscription: {str(e)}")
        
        # 2. Delete user sessions
        await db.user_sessions.delete_many({"email": email})
        
        # 3. Delete user assets
        await db.assets.delete_many({"sponsor_email": email})
        
        # 4. Delete user subscriptions
        await db.user_subscriptions.delete_many({"user_email": email})
        
        # 5. Delete payment transactions
        await db.payment_transactions.delete_many({"user_email": email})
        
        # 6. Delete sponsor record
        await db.sponsors.delete_many({"email": email})
        
        # 7. Delete registered account
        await db.registered_accounts.delete_many({"email": email})
        
        # 8. Delete user record
        await db.users.delete_many({"email": email})
        
        # 9. Update deletion request status
        await db.deletion_requests.update_one(
            {"token": data.token},
            {"$set": {
                "status": "completed",
                "confirmed_at": datetime.now(timezone.utc).isoformat(),
                "completed_at": datetime.now(timezone.utc).isoformat()
            }}
        )
        
        logger.info(f"Account deleted successfully: {email}")
        
        return {
            "success": True,
            "message": "Your account has been successfully deleted. Any active subscriptions have been cancelled."
        }
        
    except Exception as e:
        logger.error(f"Error during account deletion: {str(e)}")
        raise HTTPException(status_code=500, detail="An error occurred during account deletion. Please contact support.")


@router.get("/status/{token}")
async def get_deletion_status(token: str):
    """Check the status of a deletion request"""
    deletion = await db.deletion_requests.find_one(
        {"token": token},
        {"_id": 0, "token": 0}  # Don't expose the token
    )
    
    if not deletion:
        raise HTTPException(status_code=404, detail="Deletion request not found")
    
    return {
        "status": deletion.get("status"),
        "email": deletion.get("email"),
        "created_at": deletion.get("created_at"),
        "expires_at": deletion.get("expires_at"),
        "completed_at": deletion.get("completed_at")
    }
