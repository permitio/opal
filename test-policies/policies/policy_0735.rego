package risk.authorization.policy.verify.utils.policy_0735

# Auto-generated policy 735
# Package: risk.authorization.policy.verify.utils

# Metadata
metadata := {
    "policy_id": "0735",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0735 {
    input.user.active
    input.resource.public
}
allowed_0735 {
    data.policies.risk.enabled
}

# Utility function for user info
