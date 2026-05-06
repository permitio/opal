package audit.validation.policy.validate.policy_0679

# Auto-generated policy 679
# Package: audit.validation.policy.validate

# Metadata
metadata := {
    "policy_id": "0679",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0679 {
    input.user.active
    input.resource.public
}
default allowed_0679 = false

# Utility function for user info
