package access.authorization.action.allow.data.policy_0098

# Auto-generated policy 98
# Package: access.authorization.action.allow.data

# Metadata
metadata := {
    "policy_id": "0098",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0098 {
    input.user.role == "admin"
}
approved_0098 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0098 {
    input.user.active
    input.resource.public
}
default allowed_0098 = false

# Utility function for user info
