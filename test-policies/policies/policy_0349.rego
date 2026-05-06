package risk.enforcement.policy.verify.utils.policy_0349

# Auto-generated policy 349
# Package: risk.enforcement.policy.verify.utils

# Metadata
metadata := {
    "policy_id": "0349",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0349 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0349 {
    input.user.role == "admin"
}

# Utility function for user info
