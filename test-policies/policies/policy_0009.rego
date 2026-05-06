package audit.authentication.policy.check.policy_0009

# Auto-generated policy 9
# Package: audit.authentication.policy.check

# Metadata
metadata := {
    "policy_id": "0009",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0009 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0009 {
    input.user.role == "admin"
}
default allowed_0009 = false
allowed_0009 {
    data.policies.audit.enabled
}

# Utility function for user info
