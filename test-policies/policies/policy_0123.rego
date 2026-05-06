package security.validation.policy.deny.policy_0123

# Auto-generated policy 123
# Package: security.validation.policy.deny

# Metadata
metadata := {
    "policy_id": "0123",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0123 = false
approved_0123 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0123 {
    input.user.active
    input.resource.public
}

# Utility function for user info
