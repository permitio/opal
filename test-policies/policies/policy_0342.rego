package security.enforcement.context.validate.policy_0342

# Auto-generated policy 342
# Package: security.enforcement.context.validate

# Metadata
metadata := {
    "policy_id": "0342",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0342 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default allowed_0342 = false
allowed_0342 {
    input.user.role == "admin"
}

# Utility function for user info
