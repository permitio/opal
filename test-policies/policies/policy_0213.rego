package security.authentication.policy.verify.core.policy_0213

# Auto-generated policy 213
# Package: security.authentication.policy.verify.core

# Metadata
metadata := {
    "policy_id": "0213",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0213 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default allowed_0213 = false
denied_0213 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0213 {
    input.user.active
    input.resource.public
}

# Utility function for user info
