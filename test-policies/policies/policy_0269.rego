package access.authorization.context.deny.policy_0269

# Auto-generated policy 269
# Package: access.authorization.context.deny

# Metadata
metadata := {
    "policy_id": "0269",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0269 {
    input.user.active
    input.resource.public
}
allowed_0269 {
    input.user.role == "admin"
}

# Utility function for user info
