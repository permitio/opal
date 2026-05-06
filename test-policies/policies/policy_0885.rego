package security.monitoring.action.allow.helpers.policy_0885

# Auto-generated policy 885
# Package: security.monitoring.action.allow.helpers

# Metadata
metadata := {
    "policy_id": "0885",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0885 {
    input.user.active
    input.resource.public
}
allowed_0885 {
    input.user.role == "admin"
}
default allowed_0885 = false

# Utility function for user info
