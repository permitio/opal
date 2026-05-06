package security.authorization.action.validate.policy_0139

# Auto-generated policy 139
# Package: security.authorization.action.validate

# Metadata
metadata := {
    "policy_id": "0139",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0139 {
    input.user.active
    input.resource.public
}
default allowed_0139 = false
denied_0139 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
