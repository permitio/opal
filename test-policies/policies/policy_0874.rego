package governance.authorization.policy.validate.utils.policy_0874

# Auto-generated policy 874
# Package: governance.authorization.policy.validate.utils

# Metadata
metadata := {
    "policy_id": "0874",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0874 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default allowed_0874 = false

# Utility function for user info
