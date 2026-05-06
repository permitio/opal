package risk.authorization.resource.verify.policy_0811

# Auto-generated policy 811
# Package: risk.authorization.resource.verify

# Metadata
metadata := {
    "policy_id": "0811",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0811 {
    data.policies.risk.enabled
}
allowed_0811 {
    input.user.active
    input.resource.public
}

# Utility function for user info
