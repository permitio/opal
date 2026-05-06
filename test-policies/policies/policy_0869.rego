package audit.validation.user.validate.logic.policy_0869

# Auto-generated policy 869
# Package: audit.validation.user.validate.logic

# Metadata
metadata := {
    "policy_id": "0869",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0869 {
    input.user.role == "admin"
}
default allowed_0869 = false
allowed_0869 {
    input.user.active
    input.resource.public
}

# Utility function for user info
