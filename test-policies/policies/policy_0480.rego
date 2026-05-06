package access.enforcement.resource.deny.core.policy_0480

# Auto-generated policy 480
# Package: access.enforcement.resource.deny.core

# Metadata
metadata := {
    "policy_id": "0480",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0480 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default allowed_0480 = false
allowed_0480 {
    data.policies.access.enabled
}

# Utility function for user info
