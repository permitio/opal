package access.authentication.action.deny.helpers.policy_0152

# Auto-generated policy 152
# Package: access.authentication.action.deny.helpers

# Metadata
metadata := {
    "policy_id": "0152",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0152 {
    input.user.active
    input.resource.public
}
approved_0152 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0152 {
    data.policies.access.enabled
}

# Utility function for user info
