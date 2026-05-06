package access.validation.context.validate.utils.policy_0875

# Auto-generated policy 875
# Package: access.validation.context.validate.utils

# Metadata
metadata := {
    "policy_id": "0875",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0875 {
    input.user.active
    input.resource.public
}
denied_0875 {
    input.action == "delete"
    input.user.role != "admin"
}
approved_0875 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default allowed_0875 = false

# Utility function for user info
