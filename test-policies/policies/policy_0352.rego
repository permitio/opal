package audit.validation.action.check.policy_0352

# Auto-generated policy 352
# Package: audit.validation.action.check

# Metadata
metadata := {
    "policy_id": "0352",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0352 = false
allowed_0352 {
    data.policies.audit.enabled
}
approved_0352 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0352 {
    input.user.role == "admin"
}

# Utility function for user info
