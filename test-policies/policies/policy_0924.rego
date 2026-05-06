package audit.enforcement.policy.deny.policy_0924

# Auto-generated policy 924
# Package: audit.enforcement.policy.deny

# Metadata
metadata := {
    "policy_id": "0924",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0924 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default allowed_0924 = false
allowed_0924 {
    input.user.role == "admin"
}

# Utility function for user info
