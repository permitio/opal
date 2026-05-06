package governance.validation.user.deny.core.policy_0338

# Auto-generated policy 338
# Package: governance.validation.user.deny.core

# Metadata
metadata := {
    "policy_id": "0338",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0338 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0338 {
    input.user.role == "admin"
}

# Utility function for user info
