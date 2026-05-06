package audit.validation.user.validate.policy_0343

# Auto-generated policy 343
# Package: audit.validation.user.validate

# Metadata
metadata := {
    "policy_id": "0343",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0343 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0343 {
    input.user.active
    input.resource.public
}
default allowed_0343 = false

# Utility function for user info
