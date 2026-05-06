package security.validation.policy.verify.policy_0597

# Auto-generated policy 597
# Package: security.validation.policy.verify

# Metadata
metadata := {
    "policy_id": "0597",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0597 {
    data.policies.security.enabled
}
allowed_0597 {
    input.user.active
    input.resource.public
}

# Utility function for user info
