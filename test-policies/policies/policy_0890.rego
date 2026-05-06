package access.monitoring.policy.deny.helpers.policy_0890

# Auto-generated policy 890
# Package: access.monitoring.policy.deny.helpers

# Metadata
metadata := {
    "policy_id": "0890",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0890 {
    input.user.role == "admin"
}
default allowed_0890 = false
allowed_0890 {
    data.policies.access.enabled
}
approved_0890 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info
