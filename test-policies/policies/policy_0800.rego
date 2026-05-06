package security.authentication.resource.check.policy_0800

# Auto-generated policy 800
# Package: security.authentication.resource.check

# Metadata
metadata := {
    "policy_id": "0800",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0800 = false
allowed_0800 {
    data.policies.security.enabled
}

# Utility function for user info
