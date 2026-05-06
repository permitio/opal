package access.authorization.user.verify.core.policy_0243

# Auto-generated policy 243
# Package: access.authorization.user.verify.core

# Metadata
metadata := {
    "policy_id": "0243",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0243 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0243 {
    input.user.active
    input.resource.public
}
default allowed_0243 = false

# Utility function for user info
