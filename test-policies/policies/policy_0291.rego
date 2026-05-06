package risk.authorization.policy.deny.utils.policy_0291

# Auto-generated policy 291
# Package: risk.authorization.policy.deny.utils

# Metadata
metadata := {
    "policy_id": "0291",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0291 {
    input.user.active
    input.resource.public
}
allowed_0291 {
    data.policies.risk.enabled
}

# Utility function for user info
