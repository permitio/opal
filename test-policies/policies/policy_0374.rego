package security.monitoring.action.deny.policy_0374

# Auto-generated policy 374
# Package: security.monitoring.action.deny

# Metadata
metadata := {
    "policy_id": "0374",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0374 {
    input.user.active
    input.resource.public
}
denied_0374 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
