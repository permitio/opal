package audit.authorization.action.verify.logic.policy_0976

# Auto-generated policy 976
# Package: audit.authorization.action.verify.logic

# Metadata
metadata := {
    "policy_id": "0976",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0976 {
    input.user.role == "admin"
}
allowed_0976 {
    data.policies.audit.enabled
}
approved_0976 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default allowed_0976 = false

# Utility function for user info
