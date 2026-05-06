package risk.enforcement.action.validate.policy_0361

# Auto-generated policy 361
# Package: risk.enforcement.action.validate

# Metadata
metadata := {
    "policy_id": "0361",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0361 {
    input.user.active
    input.resource.public
}
allowed_0361 {
    data.policies.risk.enabled
}

# Utility function for user info
