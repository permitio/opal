package risk.enforcement.action.deny.utils.policy_0681

# Auto-generated policy 681
# Package: risk.enforcement.action.deny.utils

# Metadata
metadata := {
    "policy_id": "0681",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0681 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0681 {
    data.policies.risk.enabled
}
default allowed_0681 = false
approved_0681 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info
