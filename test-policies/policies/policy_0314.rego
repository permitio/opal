package audit.enforcement.user.validate.utils.policy_0314

# Auto-generated policy 314
# Package: audit.enforcement.user.validate.utils

# Metadata
metadata := {
    "policy_id": "0314",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0314 = false
allowed_0314 {
    input.user.role == "admin"
}
allowed_0314 {
    input.user.active
    input.resource.public
}

# Utility function for user info
