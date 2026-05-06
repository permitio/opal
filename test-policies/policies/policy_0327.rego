package risk.monitoring.user.validate.policy_0327

# Auto-generated policy 327
# Package: risk.monitoring.user.validate

# Metadata
metadata := {
    "policy_id": "0327",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0327 = false
denied_0327 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0327 {
    data.policies.risk.enabled
}

# Utility function for user info
