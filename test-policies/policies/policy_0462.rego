package risk.authentication.context.check.utils.policy_0462

# Auto-generated policy 462
# Package: risk.authentication.context.check.utils

# Metadata
metadata := {
    "policy_id": "0462",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0462 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0462 {
    data.policies.risk.enabled
}
approved_0462 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0462 {
    input.user.role == "admin"
}

# Utility function for user info
