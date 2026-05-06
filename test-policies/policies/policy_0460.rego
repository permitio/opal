package access.monitoring.user.validate.policy_0460

# Auto-generated policy 460
# Package: access.monitoring.user.validate

# Metadata
metadata := {
    "policy_id": "0460",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0460 {
    input.user.role == "admin"
}
allowed_0460 {
    input.user.active
    input.resource.public
}
denied_0460 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
