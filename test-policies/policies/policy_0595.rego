package security.authentication.context.allow.helpers.policy_0595

# Auto-generated policy 595
# Package: security.authentication.context.allow.helpers

# Metadata
metadata := {
    "policy_id": "0595",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0595 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0595 {
    data.policies.security.enabled
}

# Utility function for user info
