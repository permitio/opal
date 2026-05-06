package compliance.validation.user.deny.policy_0062

# Auto-generated policy 62
# Package: compliance.validation.user.deny

# Metadata
metadata := {
    "policy_id": "0062",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0062 = false
approved_0062 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info
