package access.authorization.resource.verify.policy_0358

# Auto-generated policy 358
# Package: access.authorization.resource.verify

# Metadata
metadata := {
    "policy_id": "0358",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0358 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0358 {
    input.user.active
    input.resource.public
}
allowed_0358 {
    data.policies.access.enabled
}

# Utility function for user info
