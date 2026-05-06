package risk.monitoring.policy.allow.policy_0751

# Auto-generated policy 751
# Package: risk.monitoring.policy.allow

# Metadata
metadata := {
    "policy_id": "0751",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0751 = false
allowed_0751 {
    data.policies.risk.enabled
}
denied_0751 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
