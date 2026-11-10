from typing import List, Set, Optional

# Standard permission definitions
PERMISSIONS = {
    # Floor plans & 3D objects
    "plans:read": "View floor plans and 3D scenes",
    "plans:write": "Create, edit, and delete floor plans, walls, and rooms",
    
    # Racks & devices
    "racks:read": "View rack layouts and mounted hardware",
    "racks:write": "Add, modify, and remove racks and mounted devices",
    
    # Sensors & Telemetry
    "sensors:read": "View sensor readings and heatmaps",
    "sensors:write": "Manage sensors, thresholds, and data sources",
    
    # Security Devices & Streams
    "cameras:view": "View live CCTV video feeds",
    "cameras:manage": "Configure CCTV cameras and RTSP/ONVIF streams",
    "security:read": "View smart door locks and fingerprint access logs",
    "security:write": "Manage smart doors and security access controls",
    
    # Wi-Fi Survey
    "wifi:read": "View Wi-Fi heatmaps and access points",
    "wifi:upload": "Upload Wi-Fi survey measurement points",
    
    # Administration & Audit
    "users:read": "View user accounts",
    "users:write": "Create, edit, lock, and delete user accounts",
    "roles:read": "View roles and permission sets",
    "roles:write": "Create and modify custom roles",
    "settings:read": "View system settings",
    "settings:write": "Update system configuration, database settings, themes",
    "audit:read": "View security and audit event logs",
}

# Default system roles with pre-configured permission sets
SYSTEM_ROLES = {
    "Admin": {
        "description": "Full administrative control over the entire platform",
        "is_system": True,
        "permissions": ["*"],  # Wildcard for all permissions
    },
    "Operator": {
        "description": "Floor plan, rack, and device management; live telemetry monitoring",
        "is_system": True,
        "permissions": [
            "plans:read", "plans:write",
            "racks:read", "racks:write",
            "sensors:read", "sensors:write",
            "wifi:read", "wifi:upload",
            "security:read",
        ],
    },
    "Security Officer": {
        "description": "Viewer access with camera streaming and access log monitoring",
        "is_system": True,
        "permissions": [
            "plans:read",
            "racks:read",
            "sensors:read",
            "wifi:read",
            "cameras:view",
            "security:read",
            "audit:read",
        ],
    },
    "Viewer": {
        "description": "Read-only access to 3D floor plan scenes, racks, and dashboards",
        "is_system": True,
        "permissions": [
            "plans:read",
            "racks:read",
            "sensors:read",
            "wifi:read",
        ],
    },
}


def user_has_permission(user_permissions: Set[str], required_permission: str) -> bool:
    """Check if a set of granted permissions satisfies the required permission."""
    if "*" in user_permissions:
        return True
    if required_permission in user_permissions:
        return True
    
    # Support wildcard scope checks (e.g. 'plans:*' covers 'plans:read')
    req_parts = required_permission.split(":")
    if len(req_parts) == 2:
        wildcard_perm = f"{req_parts[0]}:*"
        if wildcard_perm in user_permissions:
            return True
            
    return False

