package access.monitoring.policy.check.policy_0198

# Auto-generated policy 198
# Package: access.monitoring.policy.check

# Metadata
metadata := {
    "policy_id": "0198",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0198 = false
approved_0198 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0198 {
    input.user.role == "admin"
}

# Utility function for user info
