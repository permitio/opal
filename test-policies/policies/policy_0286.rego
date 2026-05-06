package audit.authorization.action.validate.policy_0286

# Auto-generated policy 286
# Package: audit.authorization.action.validate

# Metadata
metadata := {
    "policy_id": "0286",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0286 {
    input.user.active
    input.resource.public
}
denied_0286 {
    input.action == "delete"
    input.user.role != "admin"
}
default allowed_0286 = false

# Utility function for user info
