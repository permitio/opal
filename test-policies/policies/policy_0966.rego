package audit.authorization.user.validate.core.policy_0966

# Auto-generated policy 966
# Package: audit.authorization.user.validate.core

# Metadata
metadata := {
    "policy_id": "0966",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0966 {
    input.user.role == "admin"
}
approved_0966 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0966 {
    data.policies.audit.enabled
}

# Utility function for user info
