package access.validation.resource.verify.policy_0429

# Auto-generated policy 429
# Package: access.validation.resource.verify

# Metadata
metadata := {
    "policy_id": "0429",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0429 {
    input.user.role == "admin"
}
default allowed_0429 = false

# Utility function for user info
