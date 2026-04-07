"""Stripe Payment Integration for BIG Hat Sponsor Portal

This module handles:
- Stripe Checkout for subscription payments
- Monthly recurring subscriptions for sponsorship tiers
- Billing cycle anchor for consistent billing dates
- Automatic tax collection for compliance
- Upgrade/downgrade subscription management
- Payment status tracking and webhooks
"""

from fastapi import APIRouter, HTTPException, Query, Request

db = None
def set_database(database):
    global db
    db = database

from pydantic import BaseModel, Field
from typing import Optional
import os
import logging
from datetime import datetime, timezone
# db injected via set_database
import uuid
import stripe

# Rate limiting
from slowapi import Limiter
from slowapi.util import get_remote_address

logger = logging.getLogger(__name__)

# Initialize rate limiter for payment routes (moderate limits)
limiter = Limiter(key_func=get_remote_address)

router = APIRouter(prefix="/payments", tags=["payments"])

# Stripe Configuration (loaded from environment - NEVER hardcode)
STRIPE_API_KEY = os.environ.get("STRIPE_API_KEY", "")
STRIPE_PUBLISHABLE_KEY = os.environ.get("STRIPE_PUBLISHABLE_KEY", "")

# Initialize Stripe with the API key
stripe.api_key = STRIPE_API_KEY

# Define sponsorship packages with FIXED prices (security - never accept from frontend)
SPONSORSHIP_PACKAGES = {
    "bronze-single": {
        "name": "Bronze Sponsor (Single Location)",
        "price": 375.00,  # Monthly price
        "tier": "bronze",
        "description": "Perfect for local businesses targeting one venue",
        "features": [
            "Small logo and name in sponsor section",
            "Spot on the thank you credit",
            "One host mention",
            "Single venue coverage"
        ]
    },
    "bronze-all": {
        "name": "Bronze Sponsor (All Locations)",
        "price": 500.00,  # Monthly price
        "tier": "bronze",
        "description": "Perfect for local businesses getting started across all venues",
        "features": [
            "Small logo and name in sponsor section",
            "Spot on the thank you credit",
            "One host mention",
            "All venue coverage"
        ]
    },
    "silver": {
        "name": "Silver Sponsor",
        "price": 850.00,
        "tier": "silver",
        "description": "Enhanced visibility with social reach",
        "features": [
            "Big logo and name in sponsor section",
            "One social media promo per month",
            "One specific round hosted per month"
        ]
    },
    "gold": {
        "name": "Gold Sponsor",
        "price": 1800.00,
        "tier": "gold",
        "description": "Premium exposure across all events",
        "features": [
            "One pre-show mention each event",
            "One logo placement in a round overlay",
            "Product/service description during sponsor display",
            "Mention at every bingo and karaoke event",
            "Link/QR code for metrics tracking",
            "Access to 16:9 wide format uploads"
        ]
    },
    "star-tier": {
        "name": "Star Tier Presenter",
        "price": 4000.00,
        "tier": "gold",  # Same tier access as gold
        "description": "Maximum brand integration & exclusivity",
        "features": [
            "Presented-by title before every trivia event",
            "Pre-show promotional spot",
            "Full page sponsor section (up to 30s graphic)",
            "Host can hand out flyers or materials",
            "Custom social tags",
            "Shown at every community event",
            "Automatic entry as sponsor of the BIG Trivia tournament",
            "Access to 16:9 wide format uploads"
        ]
    },
    # À la carte items (can be purchased standalone)
    "alacarte-digital-mention": {
        "name": "Digital Mentions",
        "price": 100.00,
        "tier": "alacarte",
        "description": "Digital mention displayed during show",
        "features": ["Digital mention displayed during show"]
    },
    "alacarte-round-overlay": {
        "name": "Round Overlay",
        "price": 100.00,
        "tier": "alacarte",
        "description": "Logo displayed in round overlay",
        "features": ["Logo placement in one round overlay"]
    },
    "alacarte-answer-overlay": {
        "name": "Answer Overlay",
        "price": 150.00,
        "tier": "alacarte",
        "description": "Logo displayed in answer reveal overlay",
        "features": ["Logo placement in answer reveal"]
    },
    "alacarte-venue-sponsor-small": {
        "name": "Venue Sponsor (< 50 capacity)",
        "price": 150.00,
        "tier": "alacarte",
        "description": "Venue sponsorship for locations with < 50 capacity",
        "features": ["Venue sponsorship for one location", "25% discount for AZ local sponsors"]
    },
    "alacarte-venue-sponsor-large": {
        "name": "Venue Sponsor (> 50 capacity)",
        "price": 300.00,
        "tier": "alacarte",
        "description": "Venue sponsorship for locations with > 50 capacity",
        "features": ["Venue sponsorship for one location", "25% discount for AZ local sponsors"]
    },
    "alacarte-round-sponsor-small": {
        "name": "Round Sponsor (< 50 capacity)",
        "price": 100.00,
        "tier": "alacarte",
        "description": "Sponsor a round for 30 days at venues with < 50 capacity",
        "features": ["Round sponsorship for 30 days"]
    },
    "alacarte-round-sponsor-large": {
        "name": "Round Sponsor (> 50 capacity)",
        "price": 200.00,
        "tier": "alacarte",
        "description": "Sponsor a round for 30 days at venues with > 50 capacity",
        "features": ["Round sponsorship for 30 days"]
    },
    "alacarte-prize-sponsor": {
        "name": "Prize Sponsor",
        "price": 200.00,
        "tier": "alacarte",
        "description": "Sponsor prizes for events",
        "features": ["Prize sponsorship for events"]
    }
}


# ============ AZ Local Discount Codes ============
# These codes require an Arizona zip code to be valid
AZ_LOCAL_DISCOUNT_CODES = {"AZLOCAL25", "AZ25"}

# Arizona zip code range: 85001 to 86556
AZ_ZIP_MIN = 85001
AZ_ZIP_MAX = 86556

# ============ Stripe Price ID Mapping ============
# Maps package_id to Stripe Price ID for direct checkout
STRIPE_PRICE_IDS = {
    # Tier Packages (monthly subscriptions)
    "bronze-single": "price_1SkROcCLagab3ysjzz5cokzK",  # $375/month
    "bronze-all": "price_1SkVl8CLagab3ysjPJTfdhyy",  # $500/month
    "silver": "price_1SkQJdCLagab3ysjjVIW1UeB",  # $850/month
    "gold": "price_1SkVl8CLagab3ysjzWnvpPDI",  # $1800/month
    "star-tier": "price_1SkVl9CLagab3ysjVqF7WGsf",  # $4000/month
    
    # À La Carte Options (one-time)
    "alacarte-digital-mention": "price_1SkQPMCLagab3ysjNXgHDzE0",  # $100
    "alacarte-round-overlay": "price_1SkVl9CLagab3ysj6Ltul5ey",  # $100
    "alacarte-answer-overlay": "price_1SkVl9CLagab3ysjcbMtrhAB",  # $150
    "alacarte-venue-sponsor-small": "price_1SkVlACLagab3ysjDRw6TEPK",  # $150
    "alacarte-venue-sponsor-large": "price_1SkVlACLagab3ysjYsEeRJfA",  # $300
    "alacarte-round-sponsor-small": "price_1SkVlACLagab3ysju5hfysgQ",  # $100
    "alacarte-round-sponsor-large": "price_1SkVlBCLagab3ysjPXb8skiM",  # $200
    "alacarte-prize-sponsor": "price_1SkVlBCLagab3ysjMBK3ZWLC",  # $200
}


def is_arizona_zip_code(zip_code: str) -> bool:
    """Check if a zip code is within Arizona (85001-86556)"""
    if not zip_code:
        return False
    try:
        # Handle zip codes with extensions (e.g., 85001-1234)
        zip_num = int(zip_code.split('-')[0].strip())
        return AZ_ZIP_MIN <= zip_num <= AZ_ZIP_MAX
    except (ValueError, AttributeError):
        return False


async def get_user_zip_code(user_email: str) -> Optional[str]:
    """Get user's zip code from their account"""
    account = await db.registered_accounts.find_one(
        {"email": user_email.lower()},
        {"zip_code": 1, "_id": 0}
    )
    return account.get("zip_code") if account else None


# ============ Pydantic Models ============
class CreateCheckoutRequest(BaseModel):
    package_id: str = Field(..., description="The package ID to purchase")
    origin_url: str = Field(..., description="Frontend origin URL for redirects")
    user_email: str = Field(..., description="User email for tracking")
    discount_code: Optional[str] = Field(None, description="Optional discount code to apply")


class CheckoutResponse(BaseModel):
    url: str
    session_id: str


class PaymentStatusResponse(BaseModel):
    status: str
    payment_status: str
    amount_total: float
    currency: str
    package_id: Optional[str] = None
    package_name: Optional[str] = None


class SubscriptionInfo(BaseModel):
    id: str
    package_id: str
    package_name: str
    status: str
    amount: float
    start_date: str
    end_date: Optional[str] = None
    next_billing_date: Optional[str] = None


class UpgradeDowngradeRequest(BaseModel):
    new_package_id: str = Field(..., description="The new package to switch to")
    origin_url: str = Field(..., description="Frontend origin URL for redirects")
    user_email: str = Field(..., description="User email for tracking")
    discount_code: Optional[str] = Field(None, description="Discount code to apply")


# ============ Helper Functions ============
def get_or_create_stripe_product(package_id: str, package: dict) -> str:
    """Get or create a Stripe product and price for a package"""
    try:
        # Search for existing product
        products = stripe.Product.search(query=f"metadata['package_id']:'{package_id}'")
        
        if products.data:
            product = products.data[0]
        else:
            # Create new product
            product = stripe.Product.create(
                name=package["name"],
                description=package.get("description", ""),
                metadata={"package_id": package_id}
            )
        
        # Search for existing price
        prices = stripe.Price.list(product=product.id, active=True)
        
        # Find a matching recurring monthly price
        for price in prices.data:
            if (price.unit_amount == int(package["price"] * 100) and 
                price.recurring and 
                price.recurring.interval == "month"):
                return price.id
        
        # Create new price if not found
        price = stripe.Price.create(
            product=product.id,
            unit_amount=int(package["price"] * 100),  # Stripe uses cents
            currency="usd",
            recurring={"interval": "month"},
            metadata={"package_id": package_id}
        )
        
        return price.id
    except Exception as e:
        logger.error(f"Error creating Stripe product/price: {str(e)}")
        raise


async def activate_subscription(user_email: str, package_id: str, session_id: str, stripe_subscription_id: str = None):
    """Activate a subscription for a user after successful payment"""
    package = SPONSORSHIP_PACKAGES.get(package_id)
    if not package:
        logger.error(f"Invalid package_id: {package_id}")
        return False
    
    now = datetime.now(timezone.utc)
    
    # Calculate next billing date (1st of next month for consistent billing cycles)
    if now.month == 12:
        next_billing = now.replace(year=now.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        next_billing = now.replace(month=now.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0)
    
    # Create subscription record
    subscription = {
        "id": f"sub_{uuid.uuid4().hex[:12]}",
        "user_email": user_email.lower(),
        "package_id": package_id,
        "package_name": package["name"],
        "tier": package["tier"],
        "amount": package["price"],
        "status": "active",
        "stripe_session_id": session_id,
        "stripe_subscription_id": stripe_subscription_id,
        "start_date": now.isoformat(),
        "billing_cycle_anchor": now.isoformat(),
        "next_billing_date": next_billing.isoformat(),
        "created_at": now.isoformat(),
        "updated_at": now.isoformat()
    }
    
    # Deactivate any existing subscriptions for this user
    await db.subscriptions.update_many(
        {"user_email": user_email.lower(), "status": "active"},
        {"$set": {"status": "cancelled", "updated_at": now.isoformat()}}
    )
    
    # Insert new subscription
    await db.subscriptions.insert_one(subscription)
    
    # Update sponsor tier
    await db.sponsors.update_one(
        {"email": user_email.lower()},
        {"$set": {
            "tier": package["tier"],
            "package": package["name"],
            "status": "active",
            "updated_at": now.isoformat()
        }}
    )
    
    # Update registered account
    await db.registered_accounts.update_one(
        {"email": user_email.lower()},
        {"$set": {
            "sponsor_tier": package["tier"],
            "sponsor_package": package["name"],
            "updated_at": now.isoformat()
        }}
    )
    
    logger.info(f"Activated subscription {subscription['id']} for {user_email} - {package['name']}")
    return True


# ============ Discount Codes ============
DISCOUNT_CODES = {
    "AZLOCAL25": {
        "type": "percent",
        "value": 25,
        "description": "25% AZ Local Sponsor Discount",
        "active": True
    },
    "AZ25": {
        "type": "percent",
        "value": 25,
        "description": "25% AZ Local Sponsor Discount",
        "active": True
    },
    "WELCOME10": {
        "type": "percent",
        "value": 10,
        "description": "10% Welcome Discount",
        "active": True
    },
    "BIGHAT20": {
        "type": "percent",
        "value": 20,
        "description": "20% BIG Hat Special Discount",
        "active": True
    },
    "99-SPONSOR-99": {
        "type": "fixed_price",
        "value": 1.00,  # Final price will be $1.00
        "description": "Test Purchase - Prize Sponsor $1",
        "active": True,
        "one_time": True,  # Will be deleted after use
        "restricted_to": ["alacarte-prize-sponsor"],  # Only works for Prize Sponsor
        "usage_count": 0
    }
}


# ============ API Endpoints ============
@router.get("/config")
async def get_stripe_config():
    """Get Stripe publishable key for frontend - NEVER expose secret key"""
    if not STRIPE_PUBLISHABLE_KEY:
        raise HTTPException(status_code=500, detail="Stripe not configured")
    return {
        "publishable_key": STRIPE_PUBLISHABLE_KEY
    }


@router.get("/discount/validate")
async def validate_discount_code(code: str, user_email: Optional[str] = None, package_id: Optional[str] = None):
    """Validate a discount code. AZ local discounts require an Arizona zip code.
    Special codes may be restricted to specific packages."""
    code = code.strip().upper()
    discount = DISCOUNT_CODES.get(code)
    
    if not discount or not discount.get("active", False):
        return {
            "valid": False,
            "message": "Invalid or expired discount code"
        }
    
    # Check if this is a restricted code (only works for specific packages)
    restricted_to = discount.get("restricted_to", [])
    if restricted_to:
        if not package_id:
            return {
                "valid": True,  # Valid but will need package check at checkout
                "code": code,
                "type": discount["type"],
                "value": discount["value"],
                "description": discount["description"],
                "restricted_to": restricted_to,
                "message": f"This code is only valid for: {', '.join(restricted_to)}"
            }
        if package_id not in restricted_to:
            return {
                "valid": False,
                "message": "This discount code is only valid for Prize Sponsor purchases."
            }
    
    # Check if this is an AZ local discount code
    if code in AZ_LOCAL_DISCOUNT_CODES:
        # Require user_email to validate AZ zip code
        if not user_email:
            return {
                "valid": False,
                "requires_zip": True,
                "message": "AZ local discounts require zip code verification. Please update your profile."
            }
        
        # Get user's zip code
        user_zip = await get_user_zip_code(user_email)
        
        if not user_zip:
            return {
                "valid": False,
                "requires_zip": True,
                "message": "Please add your zip code to your profile to use AZ local discounts."
            }
        
        if not is_arizona_zip_code(user_zip):
            return {
                "valid": False,
                "not_az_resident": True,
                "message": f"AZ local discounts are only available for Arizona residents (zip codes 85001-86556). Your zip code: {user_zip}"
            }
    
    return {
        "valid": True,
        "code": code,
        "type": discount["type"],
        "value": discount["value"],
        "description": discount["description"],
        "restricted_to": restricted_to if restricted_to else None
    }


@router.get("/packages")
async def get_packages():
    """Get all available sponsorship packages"""
    packages = []
    for pkg_id, pkg in SPONSORSHIP_PACKAGES.items():
        packages.append({
            "id": pkg_id,
            "name": pkg["name"],
            "price": pkg["price"],
            "description": pkg["description"],
            "features": pkg["features"],
            "tier": pkg["tier"]
        })
    return packages


@router.post("/checkout/session", response_model=CheckoutResponse)
@limiter.limit("20/minute")  # Limit checkout attempts to 20 per minute per IP
async def create_checkout_session(request: Request, data: CreateCheckoutRequest):
    """Create a Stripe Checkout session for subscription or one-time purchase with:
    - Monthly recurring billing for tier packages
    - One-time payment for à la carte items
    - Automatic tax collection (if enabled in Stripe Dashboard)
    - Billing cycle anchor for consistent billing dates (subscriptions only)
    - Customer tax information collection
    """
    
    # Validate package exists (SECURITY: price comes from server, not frontend)
    package = SPONSORSHIP_PACKAGES.get(data.package_id)
    if not package:
        raise HTTPException(status_code=400, detail="Invalid package selected")
    
    if not STRIPE_API_KEY:
        raise HTTPException(status_code=500, detail="Stripe API key not configured")
    
    # Determine if this is a subscription or one-time payment
    is_alacarte = package.get("tier") == "alacarte"
    
    # Build success/cancel URLs from frontend origin
    success_url = f"{data.origin_url}/dashboard/subscribe?session_id={{CHECKOUT_SESSION_ID}}&success=true"
    cancel_url = f"{data.origin_url}/dashboard/subscribe?cancelled=true"
    
    try:
        # Use pre-configured Stripe Price ID if available, otherwise create dynamically
        price_id = STRIPE_PRICE_IDS.get(data.package_id)
        if not price_id:
            # Fall back to dynamic creation for packages not in the mapping
            price_id = get_or_create_stripe_product(data.package_id, package)
        
        # Handle special discount codes (like 99-SPONSOR-99)
        stripe_coupon_id = None
        special_discount_code = None
        
        if data.discount_code:
            discount_code_upper = data.discount_code.strip().upper()
            discount = DISCOUNT_CODES.get(discount_code_upper)
            
            if discount and discount.get("active"):
                # Check if this is a restricted discount code
                restricted_to = discount.get("restricted_to", [])
                if restricted_to and data.package_id not in restricted_to:
                    raise HTTPException(
                        status_code=400, 
                        detail=f"Discount code '{discount_code_upper}' is only valid for: {', '.join(restricted_to)}"
                    )
                
                # Handle fixed_price discount type (like 99-SPONSOR-99)
                if discount["type"] == "fixed_price":
                    # Create a Stripe coupon for the discount amount
                    original_price = package["price"]
                    final_price = discount["value"]  # $1.00
                    discount_amount = original_price - final_price  # $199
                    
                    # Create a one-time Stripe coupon
                    coupon = stripe.Coupon.create(
                        amount_off=int(discount_amount * 100),  # In cents
                        currency="usd",
                        duration="once",
                        name=f"Test Purchase Discount - {discount_code_upper}",
                        max_redemptions=1,  # One-time use
                        metadata={
                            "code": discount_code_upper,
                            "type": "test_purchase"
                        }
                    )
                    stripe_coupon_id = coupon.id
                    special_discount_code = discount_code_upper
                    logger.info(f"Created one-time Stripe coupon {coupon.id} for code {discount_code_upper}")
        
        # Build checkout session parameters based on purchase type
        if is_alacarte:
            # One-time payment for à la carte items
            checkout_params = {
                "mode": "payment",
                "payment_method_types": ["card"],
                "line_items": [{
                    "price": price_id,
                    "quantity": 1,
                }],
                "success_url": success_url,
                "cancel_url": cancel_url,
                "customer_email": data.user_email,
                "metadata": {
                    "package_id": data.package_id,
                    "package_name": package["name"],
                    "user_email": data.user_email,
                    "type": "one_time",
                    "discount_code": special_discount_code or ""
                },
                "billing_address_collection": "required",
                "automatic_tax": {
                    "enabled": True
                },
            }
            
            # Apply coupon if created
            if stripe_coupon_id:
                checkout_params["discounts"] = [{"coupon": stripe_coupon_id}]
            else:
                checkout_params["allow_promotion_codes"] = True
                
        else:
            # Subscription for tier packages
            # Calculate billing cycle anchor (1st of next month for consistent billing)
            now = datetime.now(timezone.utc)
            if now.month == 12:
                billing_anchor = int(now.replace(year=now.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0).timestamp())
            else:
                billing_anchor = int(now.replace(month=now.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0).timestamp())
            
            checkout_params = {
                "mode": "subscription",
                "payment_method_types": ["card"],
                "line_items": [{
                    "price": price_id,
                    "quantity": 1,
                }],
                "success_url": success_url,
                "cancel_url": cancel_url,
                "customer_email": data.user_email,
                "metadata": {
                    "package_id": data.package_id,
                    "package_name": package["name"],
                    "user_email": data.user_email,
                    "type": "subscription"
                },
                # Collect billing address for tax purposes
                "billing_address_collection": "required",
                # Collect tax ID information
                "tax_id_collection": {
                    "enabled": True
                },
                # Subscription-specific settings
                "subscription_data": {
                    "metadata": {
                        "package_id": data.package_id,
                        "package_name": package["name"],
                        "user_email": data.user_email
                    },
                    # Set billing cycle anchor to 1st of next month
                    "billing_cycle_anchor": billing_anchor,
                    # Prorate the first payment based on when they signed up
                    "proration_behavior": "create_prorations",
                },
                # Enable automatic tax collection (requires Stripe Tax to be enabled in dashboard)
                "automatic_tax": {
                    "enabled": True
                },
                # Allow promotion codes (for discount codes in Stripe)
                "allow_promotion_codes": True,
            }
        
        # Handle regular discount code if provided (for percentage discounts)
        if data.discount_code and not stripe_coupon_id:
            discount = DISCOUNT_CODES.get(data.discount_code.strip().upper())
            if discount and discount.get("active"):
                # Note: For Stripe native discounts, you'd create a Stripe Coupon
                # For now, we'll apply the discount in the metadata for tracking
                checkout_params["metadata"]["discount_code"] = data.discount_code.strip().upper()
                checkout_params["metadata"]["discount_type"] = discount["type"]
                checkout_params["metadata"]["discount_value"] = str(discount["value"])
        
        # Create the checkout session
        session = stripe.checkout.Session.create(**checkout_params)
        
        # Create payment transaction record
        transaction = {
            "id": f"txn_{uuid.uuid4().hex[:12]}",
            "session_id": session.id,
            "user_email": data.user_email.lower(),
            "package_id": data.package_id,
            "package_name": package["name"],
            "amount": package["price"],
            "currency": "usd",
            "status": "pending",
            "payment_status": "initiated",
            "is_alacarte": is_alacarte,
            "stripe_coupon_id": stripe_coupon_id,
            "discount_code": data.discount_code.strip().upper() if data.discount_code else None,
            "automatic_tax_enabled": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        
        if not is_alacarte:
            transaction["billing_cycle_anchor"] = billing_anchor
        
        await db.payment_transactions.insert_one(transaction)
        
        logger.info(f"Created checkout session {session.id} for {data.user_email} - {package['name']} ({'one-time' if is_alacarte else 'subscription'})")
        
        return CheckoutResponse(url=session.url, session_id=session.id)
        
    except stripe.error.StripeError as e:
        logger.error(f"Stripe error creating checkout session: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Payment service error: {str(e)}")
    except Exception as e:
        logger.error(f"Failed to create checkout session: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to create checkout session: {str(e)}")


@router.get("/checkout/status/{session_id}", response_model=PaymentStatusResponse)
async def get_checkout_status(request: Request, session_id: str):
    """Get the status of a checkout session and update database if paid"""
    
    try:
        # Retrieve the session from Stripe
        session = stripe.checkout.Session.retrieve(session_id)
        
        # Get transaction from database
        transaction = await db.payment_transactions.find_one(
            {"session_id": session_id},
            {"_id": 0}
        )
        
        if not transaction:
            raise HTTPException(status_code=404, detail="Transaction not found")
        
        # Determine payment status
        payment_status = "unpaid"
        if session.payment_status == "paid":
            payment_status = "paid"
        elif session.status == "expired":
            payment_status = "expired"
        
        # Update transaction status
        now = datetime.now(timezone.utc).isoformat()
        
        if payment_status == "paid" and transaction.get("payment_status") != "paid":
            # Payment successful - update transaction
            await db.payment_transactions.update_one(
                {"session_id": session_id},
                {"$set": {
                    "status": "completed",
                    "payment_status": "paid",
                    "stripe_subscription_id": session.subscription,
                    "updated_at": now
                }}
            )
            
            # Check if this used a one-time discount code
            discount_code = transaction.get("discount_code")
            if discount_code:
                discount = DISCOUNT_CODES.get(discount_code)
                if discount and discount.get("one_time"):
                    # Deactivate the one-time discount code
                    DISCOUNT_CODES[discount_code]["active"] = False
                    DISCOUNT_CODES[discount_code]["usage_count"] = discount.get("usage_count", 0) + 1
                    DISCOUNT_CODES[discount_code]["used_by"] = transaction.get("user_email")
                    DISCOUNT_CODES[discount_code]["used_at"] = now
                    logger.info(f"One-time discount code '{discount_code}' has been deactivated after successful use")
            
            # Check if this is an à la carte item or subscription
            is_alacarte = transaction.get("is_alacarte", False)
            
            if not is_alacarte:
                # Activate the subscription for tier packages
                await activate_subscription(
                    user_email=transaction.get("user_email"),
                    package_id=transaction.get("package_id"),
                    session_id=session_id,
                    stripe_subscription_id=session.subscription
                )
                logger.info(f"Subscription payment completed for session {session_id}, subscription: {session.subscription}")
            else:
                # Record the à la carte purchase
                user_email = transaction.get("user_email").lower()
                purchase = {
                    "id": f"purchase_{uuid.uuid4().hex[:12]}",
                    "user_email": user_email,
                    "item_id": transaction.get("package_id"),
                    "item_name": transaction.get("package_name"),
                    "amount": transaction.get("amount"),
                    "discount_code": discount_code,
                    "session_id": session_id,
                    "stripe_payment_intent": session.payment_intent,
                    "status": "completed",
                    "purchased_at": now
                }
                await db.alacarte_purchases.insert_one(purchase)
                
                # Also create/update sponsor profile for à la carte purchaser
                # Check if sponsor already exists
                existing_sponsor = await db.sponsors.find_one({"email": user_email})
                
                if not existing_sponsor:
                    # Get user info from registered_accounts
                    user_account = await db.registered_accounts.find_one({"email": user_email})
                    
                    # Create a new sponsor profile
                    new_sponsor = {
                        "id": f"sponsor_{uuid.uuid4().hex[:12]}",
                        "email": user_email,
                        "business_name": user_account.get("business_name") if user_account else user_email.split("@")[0],
                        "contact_name": user_account.get("name") if user_account else None,
                        "phone": user_account.get("phone") if user_account else None,
                        "tier": None,  # No tier for à la carte only
                        "package": None,
                        "status": "active",  # Active because they made a purchase
                        "is_venue_sponsor": False,
                        "alacarte_items": [transaction.get("package_id")],
                        "created_at": now,
                        "updated_at": now
                    }
                    await db.sponsors.insert_one(new_sponsor)
                    logger.info(f"Created sponsor profile for à la carte purchaser: {user_email}")
                else:
                    # Update existing sponsor - add à la carte item to their list
                    alacarte_items = existing_sponsor.get("alacarte_items", [])
                    if transaction.get("package_id") not in alacarte_items:
                        alacarte_items.append(transaction.get("package_id"))
                    
                    # Keep existing tier/package if they have one, but ensure status is active
                    update_data = {
                        "alacarte_items": alacarte_items,
                        "status": "active",
                        "updated_at": now
                    }
                    await db.sponsors.update_one(
                        {"email": user_email},
                        {"$set": update_data}
                    )
                    logger.info(f"Updated sponsor profile with à la carte purchase: {user_email}")
                
                logger.info(f"À la carte payment completed for session {session_id}: {transaction.get('package_name')}")
            
        elif session.status == "expired":
            await db.payment_transactions.update_one(
                {"session_id": session_id},
                {"$set": {
                    "status": "expired",
                    "payment_status": "expired",
                    "updated_at": now
                }}
            )
        
        return PaymentStatusResponse(
            status=session.status,
            payment_status=payment_status,
            amount_total=(session.amount_total or 0) / 100,  # Convert cents to dollars
            currency=session.currency or "usd",
            package_id=transaction.get("package_id"),
            package_name=transaction.get("package_name")
        )
        
    except stripe.error.StripeError as e:
        logger.error(f"Stripe error getting checkout status: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Payment service error: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get checkout status: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get checkout status: {str(e)}")


@router.get("/subscription/{user_email}", response_model=Optional[SubscriptionInfo])
async def get_user_subscription(user_email: str):
    """Get active subscription for a user"""
    subscription = await db.subscriptions.find_one(
        {"user_email": user_email.lower(), "status": "active"},
        {"_id": 0}
    )
    
    if not subscription:
        return None
    
    return SubscriptionInfo(
        id=subscription.get("id"),
        package_id=subscription.get("package_id"),
        package_name=subscription.get("package_name"),
        status=subscription.get("status"),
        amount=subscription.get("amount"),
        start_date=subscription.get("start_date"),
        end_date=subscription.get("end_date"),
        next_billing_date=subscription.get("next_billing_date")
    )


@router.post("/upgrade-downgrade", response_model=CheckoutResponse)
async def upgrade_downgrade_subscription(request: Request, data: UpgradeDowngradeRequest):
    """Create a checkout session for upgrading or downgrading subscription"""
    
    # Validate new package
    new_package = SPONSORSHIP_PACKAGES.get(data.new_package_id)
    if not new_package:
        raise HTTPException(status_code=400, detail="Invalid package selected")
    
    # Check if user has an active subscription
    current_sub = await db.subscriptions.find_one(
        {"user_email": data.user_email.lower(), "status": "active"},
        {"_id": 0}
    )
    
    if current_sub and current_sub.get("package_id") == data.new_package_id:
        raise HTTPException(status_code=400, detail="Already subscribed to this package")
    
    # Determine if this is an upgrade or downgrade
    current_price = SPONSORSHIP_PACKAGES.get(current_sub.get("package_id", ""), {}).get("price", 0) if current_sub else 0
    action = "upgrade" if new_package["price"] > current_price else "downgrade"
    
    # Build success/cancel URLs
    success_url = f"{data.origin_url}/dashboard/subscribe?session_id={{CHECKOUT_SESSION_ID}}&{action}=true"
    cancel_url = f"{data.origin_url}/dashboard/subscribe?cancelled=true"
    
    try:
        # Get or create the Stripe price for this package
        price_id = get_or_create_stripe_product(data.new_package_id, new_package)
        
        # Calculate billing cycle anchor (maintain consistent billing)
        now = datetime.now(timezone.utc)
        if now.month == 12:
            billing_anchor = int(now.replace(year=now.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0).timestamp())
        else:
            billing_anchor = int(now.replace(month=now.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0).timestamp())
        
        # Create checkout session with native Stripe
        session = stripe.checkout.Session.create(
            mode="subscription",
            payment_method_types=["card"],
            line_items=[{
                "price": price_id,
                "quantity": 1,
            }],
            success_url=success_url,
            cancel_url=cancel_url,
            customer_email=data.user_email,
            metadata={
                "package_id": data.new_package_id,
                "package_name": new_package["name"],
                "user_email": data.user_email,
                "type": action,
                "previous_package": current_sub.get("package_id") if current_sub else None
            },
            billing_address_collection="required",
            tax_id_collection={"enabled": True},
            subscription_data={
                "metadata": {
                    "package_id": data.new_package_id,
                    "package_name": new_package["name"],
                    "user_email": data.user_email
                },
                "billing_cycle_anchor": billing_anchor,
                "proration_behavior": "create_prorations",
            },
            automatic_tax={"enabled": True},
            allow_promotion_codes=True,
        )
        
        # Create payment transaction record
        transaction = {
            "id": f"txn_{uuid.uuid4().hex[:12]}",
            "session_id": session.id,
            "user_email": data.user_email.lower(),
            "package_id": data.new_package_id,
            "package_name": new_package["name"],
            "amount": new_package["price"],
            "currency": "usd",
            "status": "pending",
            "payment_status": "initiated",
            "type": action,
            "previous_package_id": current_sub.get("package_id") if current_sub else None,
            "billing_cycle_anchor": billing_anchor,
            "automatic_tax_enabled": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        
        await db.payment_transactions.insert_one(transaction)
        
        logger.info(f"Created {action} checkout session {session.id} for {data.user_email}")
        
        return CheckoutResponse(url=session.url, session_id=session.id)
        
    except stripe.error.StripeError as e:
        logger.error(f"Stripe error creating checkout session: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Payment service error: {str(e)}")
    except Exception as e:
        logger.error(f"Failed to create checkout session: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to create checkout session: {str(e)}")


@router.post("/cancel/{user_email}")
async def cancel_subscription(user_email: str):
    """Cancel a user's active subscription"""
    result = await db.subscriptions.update_one(
        {"user_email": user_email.lower(), "status": "active"},
        {"$set": {
            "status": "cancelled",
            "cancelled_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="No active subscription found")
    
    # Update sponsor status
    await db.sponsors.update_one(
        {"email": user_email.lower()},
        {"$set": {"status": "inactive"}}
    )
    
    logger.info(f"Cancelled subscription for {user_email}")
    return {"success": True, "message": "Subscription cancelled"}


@router.get("/history/{user_email}")
async def get_payment_history(user_email: str, limit: int = Query(10, le=50)):
    """Get payment history for a user"""
    transactions = await db.payment_transactions.find(
        {"user_email": user_email.lower()},
        {"_id": 0}
    ).sort("created_at", -1).to_list(limit)
    
    return transactions
