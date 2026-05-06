package risk.enforcement.policy.verify.policy_0359

# Auto-generated policy 359
# Package: risk.enforcement.policy.verify

# Metadata
metadata := {
    "policy_id": "0359",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0359 {
    input.user.active
    input.resource.public
}
allowed_0359 {
    data.policies.risk.enabled
}

# Utility function for user info
