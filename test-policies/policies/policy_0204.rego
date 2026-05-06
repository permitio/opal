package governance.monitoring.user.allow.policy_0204

# Auto-generated policy 204
# Package: governance.monitoring.user.allow

# Metadata
metadata := {
    "policy_id": "0204",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0204 {
    input.user.role == "admin"
}
allowed_0204 {
    input.user.active
    input.resource.public
}

# Utility function for user info
