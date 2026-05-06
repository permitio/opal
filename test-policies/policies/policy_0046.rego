package governance.monitoring.user.allow.utils.policy_0046

# Auto-generated policy 46
# Package: governance.monitoring.user.allow.utils

# Metadata
metadata := {
    "policy_id": "0046",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0046 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0046 {
    input.user.role == "admin"
}

# Utility function for user info
