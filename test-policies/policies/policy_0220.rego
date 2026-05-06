package governance.validation.user.check.policy_0220

# Auto-generated policy 220
# Package: governance.validation.user.check

# Metadata
metadata := {
    "policy_id": "0220",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0220 {
    input.user.active
    input.resource.public
}
allowed_0220 {
    data.policies.governance.enabled
}

# Utility function for user info
