package security.monitoring.resource.validate.policy_0661

# Auto-generated policy 661
# Package: security.monitoring.resource.validate

# Metadata
metadata := {
    "policy_id": "0661",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0661 {
    input.user.active
    input.resource.public
}
denied_0661 {
    input.action == "delete"
    input.user.role != "admin"
}
default allowed_0661 = false

# Utility function for user info
