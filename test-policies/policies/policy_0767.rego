package access.authentication.resource.validate.policy_0767

# Auto-generated policy 767
# Package: access.authentication.resource.validate

# Metadata
metadata := {
    "policy_id": "0767",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0767 = false
allowed_0767 {
    data.policies.access.enabled
}

# Utility function for user info
