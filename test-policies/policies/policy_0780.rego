package access.monitoring.action.deny.utils.policy_0780

# Auto-generated policy 780
# Package: access.monitoring.action.deny.utils

# Metadata
metadata := {
    "policy_id": "0780",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0780 {
    input.action == "delete"
    input.user.role != "admin"
}
default allowed_0780 = false
allowed_0780 {
    data.policies.access.enabled
}
approved_0780 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info
