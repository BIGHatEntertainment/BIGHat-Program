from fastapi import APIRouter, HTTPException, Query

db = None
def set_database(database):
    global db
    db = database

from typing import List, Optional
from datetime import datetime, timedelta
import logging

from sponsor_models.schemas import Subscription, SubscriptionCreate
# db injected via set_database

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])


@router.get("", response_model=List[Subscription])
async def get_subscriptions(
    user_id: Optional[str] = Query(None, description="Filter by user ID"),
    status: Optional[str] = Query(None, description="Filter by status")
):
    """Get all subscriptions with optional filtering"""
    query = {}
    if user_id:
        query["user_id"] = user_id
    if status:
        query["status"] = status
    
    subscriptions = await db.subscriptions.find(query, {"_id": 0}).to_list(1000)
    return subscriptions


@router.get("/user/{user_id}/active", response_model=Optional[Subscription])
async def get_active_subscription(user_id: str):
    """Get the active subscription for a user"""
    today = datetime.utcnow().strftime("%Y-%m-%d")
    
    subscription = await db.subscriptions.find_one(
        {
            "user_id": user_id,
            "status": "active",
            "end_date": {"$gte": today}
        },
        {"_id": 0}
    )
    
    return subscription


@router.get("/{subscription_id}", response_model=Subscription)
async def get_subscription(subscription_id: str):
    """Get a specific subscription by ID"""
    subscription = await db.subscriptions.find_one({"id": subscription_id}, {"_id": 0})
    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")
    return subscription


@router.post("", response_model=Subscription)
async def create_subscription(sub_data: SubscriptionCreate):
    """Create a new subscription (purchase)"""
    # Calculate end date (30 days from now)
    start_date = datetime.utcnow()
    end_date = start_date + timedelta(days=30)
    
    subscription = Subscription(
        **sub_data.model_dump(),
        start_date=start_date.strftime("%Y-%m-%d"),
        end_date=end_date.strftime("%Y-%m-%d")
    )
    subscription_dict = subscription.model_dump()
    
    await db.subscriptions.insert_one(subscription_dict)
    
    # Update sponsor status to active
    await db.sponsors.update_one(
        {"email": sub_data.user_id},  # user_id is email for now
        {"$set": {"status": "active", "package": sub_data.package_name}}
    )
    
    logger.info(f"Created subscription: {sub_data.package_name} for user {sub_data.user_id}")
    return subscription


@router.post("/{subscription_id}/cancel")
async def cancel_subscription(subscription_id: str):
    """Cancel a subscription"""
    result = await db.subscriptions.update_one(
        {"id": subscription_id},
        {"$set": {"status": "cancelled"}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Subscription not found")
    
    logger.info(f"Cancelled subscription: {subscription_id}")
    return {"message": "Subscription cancelled successfully"}
