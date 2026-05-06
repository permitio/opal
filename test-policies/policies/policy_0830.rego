package access.authorization.context.allow.core.policy_0830

# Auto-generated policy 830
# Package: access.authorization.context.allow.core

# Metadata
metadata := {
    "policy_id": "0830",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0830 {
    input.user.active
    input.resource.public
}
denied_0830 {
    input.action == "delete"
    input.user.role != "admin"
}
approved_0830 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default allowed_0830 = false

# Utility function for user info
