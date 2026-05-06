package access.authorization.user.validate.core.policy_0774

# Auto-generated policy 774
# Package: access.authorization.user.validate.core

# Metadata
metadata := {
    "policy_id": "0774",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0774 = false
allowed_0774 {
    input.user.active
    input.resource.public
}
denied_0774 {
    input.action == "delete"
    input.user.role != "admin"
}
approved_0774 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info
