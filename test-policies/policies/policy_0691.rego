package risk.authentication.action.verify.core.policy_0691

# Auto-generated policy 691
# Package: risk.authentication.action.verify.core

# Metadata
metadata := {
    "policy_id": "0691",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0691 {
    input.user.role == "admin"
}
denied_0691 {
    input.action == "delete"
    input.user.role != "admin"
}
approved_0691 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default allowed_0691 = false

# Utility function for user info
