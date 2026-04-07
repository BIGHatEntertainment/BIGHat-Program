"""Sponsor Portal - Main Router Module"""
from fastapi import APIRouter
from motor.motor_asyncio import AsyncIOMotorDatabase
import logging
import os

router = APIRouter(prefix="/sponsor", tags=["sponsor"])
logger = logging.getLogger(__name__)

db = None

def set_database(database):
    global db
    db = database
    # Pass db to all sub-route modules
    for mod_name in ['auth', 'sponsors', 'accounts', 'assets', 'placements', 'locations', 'payments', 'subscriptions', 'canva', 'sharepoint', 'profile', 'webhooks', 'account_deletion']:
        try:
            mod = __import__(f'sponsor_routes.{mod_name}', fromlist=[mod_name])
            if hasattr(mod, 'set_database'):
                mod.set_database(database)
            elif hasattr(mod, 'db'):
                mod.db = database
            # Include sub-router
            if hasattr(mod, 'router'):
                router.include_router(mod.router)
                logger.info(f"  Mounted sponsor sub-route: {mod_name}")
        except Exception as e:
            logger.warning(f"  Could not load sponsor route {mod_name}: {e}")
