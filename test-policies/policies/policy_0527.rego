package risk.monitoring.user.validate.policy_0527

# Auto-generated policy 527
# Package: risk.monitoring.user.validate

# Metadata
metadata := {
    "policy_id": "0527",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0527 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0527 {
    data.policies.risk.enabled
}

# Utility function for user info
