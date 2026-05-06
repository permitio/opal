package risk.monitoring.policy.allow.policy_0061

# Auto-generated policy 61
# Package: risk.monitoring.policy.allow

# Metadata
metadata := {
    "policy_id": "0061",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0061 {
    input.user.active
    input.resource.public
}
allowed_0061 {
    input.user.role == "admin"
}

# Utility function for user info
