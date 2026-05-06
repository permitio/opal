package security.authentication.user.allow.utils.policy_0695

# Auto-generated policy 695
# Package: security.authentication.user.allow.utils

# Metadata
metadata := {
    "policy_id": "0695",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0695 {
    input.user.active
    input.resource.public
}
denied_0695 {
    input.action == "delete"
    input.user.role != "admin"
}
approved_0695 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info
