package risk.monitoring.policy.deny.helpers.policy_0192

# Auto-generated policy 192
# Package: risk.monitoring.policy.deny.helpers

# Metadata
metadata := {
    "policy_id": "0192",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0192 {
    input.user.active
    input.resource.public
}
default allowed_0192 = false
allowed_0192 {
    input.user.role == "admin"
}

# Utility function for user info
