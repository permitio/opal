package access.enforcement.policy.check.core.policy_0215

# Auto-generated policy 215
# Package: access.enforcement.policy.check.core

# Metadata
metadata := {
    "policy_id": "0215",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0215 {
    input.action == "delete"
    input.user.role != "admin"
}
default allowed_0215 = false
approved_0215 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0215 {
    input.user.role == "admin"
}

# Utility function for user info
