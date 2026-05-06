package audit.authentication.action.check.core.policy_0100

# Auto-generated policy 100
# Package: audit.authentication.action.check.core

# Metadata
metadata := {
    "policy_id": "0100",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0100 = false
approved_0100 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0100 {
    data.policies.audit.enabled
}
allowed_0100 {
    input.user.active
    input.resource.public
}

# Utility function for user info
