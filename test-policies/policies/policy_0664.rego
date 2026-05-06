package access.authorization.policy.allow.core.policy_0664

# Auto-generated policy 664
# Package: access.authorization.policy.allow.core

# Metadata
metadata := {
    "policy_id": "0664",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0664 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default allowed_0664 = false
allowed_0664 {
    input.user.active
    input.resource.public
}

# Utility function for user info
