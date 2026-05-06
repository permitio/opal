package risk.monitoring.policy.deny.policy_0160

# Auto-generated policy 160
# Package: risk.monitoring.policy.deny

# Metadata
metadata := {
    "policy_id": "0160",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0160 {
    data.policies.risk.enabled
}
allowed_0160 {
    input.user.role == "admin"
}

# Utility function for user info
