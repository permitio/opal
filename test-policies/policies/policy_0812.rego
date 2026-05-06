package compliance.validation.user.check.policy_0812

# Auto-generated policy 812
# Package: compliance.validation.user.check

# Metadata
metadata := {
    "policy_id": "0812",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0812 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default allowed_0812 = false
allowed_0812 {
    input.user.role == "admin"
}

# Utility function for user info
