package access.authorization.policy.validate.policy_0769

# Auto-generated policy 769
# Package: access.authorization.policy.validate

# Metadata
metadata := {
    "policy_id": "0769",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0769 {
    input.user.role == "admin"
}
default allowed_0769 = false

# Utility function for user info
