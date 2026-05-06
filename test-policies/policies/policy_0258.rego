package access.enforcement.context.validate.data.policy_0258

# Auto-generated policy 258
# Package: access.enforcement.context.validate.data

# Metadata
metadata := {
    "policy_id": "0258",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0258 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0258 {
    input.user.active
    input.resource.public
}
default allowed_0258 = false
denied_0258 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
