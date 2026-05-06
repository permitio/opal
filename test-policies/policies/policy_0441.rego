package security.enforcement.user.validate.policy_0441

# Auto-generated policy 441
# Package: security.enforcement.user.validate

# Metadata
metadata := {
    "policy_id": "0441",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0441 {
    input.user.active
    input.resource.public
}
default allowed_0441 = false
allowed_0441 {
    input.user.role == "admin"
}

# Utility function for user info
