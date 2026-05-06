package security.monitoring.resource.allow.policy_0055

# Auto-generated policy 55
# Package: security.monitoring.resource.allow

# Metadata
metadata := {
    "policy_id": "0055",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0055 {
    input.user.active
    input.resource.public
}
denied_0055 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
