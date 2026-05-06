package security.authentication.resource.deny.core.policy_0109

# Auto-generated policy 109
# Package: security.authentication.resource.deny.core

# Metadata
metadata := {
    "policy_id": "0109",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0109 {
    data.policies.security.enabled
}
approved_0109 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info
