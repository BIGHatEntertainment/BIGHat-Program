import uuid
from typing import List, Optional
from pydantic import BaseModel

class LicenseStatus(BaseModel):
    key: str
    master_admin_email: str
    total_seats_allowed: int = 5
    active_seats: List[str] = [] # List of unique HWIDs
    is_active: bool = True

def register_new_seat(config: dict, instance_id: str) -> bool:
    """Registers a new device seat if capacity allows."""
    license_data = config.get("license_status", {})
    active_seats = license_data.get("active_seats", [])
    max_seats = license_data.get("total_seats_allowed", 5)
    
    if instance_id in active_seats:
        return True
        
    if len(active_seats) < max_seats:
        active_seats.append(instance_id)
        license_data["active_seats"] = active_seats
        return True
        
    return False

def check_seat_validity(config: dict, instance_id: str) -> bool:
    """Verifies if this specific instance is authorized to run."""
    license_data = config.get("license_status", {})
    return instance_id in license_data.get("active_seats", [])
