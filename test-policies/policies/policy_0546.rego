package risk.authentication.policy.allow.core.policy_0546

# Auto-generated policy 546
# Package: risk.authentication.policy.allow.core

# Metadata
metadata := {
    "policy_id": "0546",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0546 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default allowed_0546 = false

# Utility function for user info
