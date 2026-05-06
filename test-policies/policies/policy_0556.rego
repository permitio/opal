package risk.monitoring.user.validate.policy_0556

# Auto-generated policy 556
# Package: risk.monitoring.user.validate

# Metadata
metadata := {
    "policy_id": "0556",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0556 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default allowed_0556 = false

# Utility function for user info
