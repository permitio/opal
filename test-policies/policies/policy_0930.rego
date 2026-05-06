package access.validation.context.verify.policy_0930

# Auto-generated policy 930
# Package: access.validation.context.verify

# Metadata
metadata := {
    "policy_id": "0930",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0930 {
    data.policies.access.enabled
}
default allowed_0930 = false
allowed_0930 {
    input.user.role == "admin"
}

# Utility function for user info
