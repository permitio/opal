package risk.monitoring.policy.deny.utils.policy_0090

# Auto-generated policy 90
# Package: risk.monitoring.policy.deny.utils

# Metadata
metadata := {
    "policy_id": "0090",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0090 {
    input.user.role == "admin"
}
denied_0090 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0090 {
    data.policies.risk.enabled
}

# Utility function for user info
