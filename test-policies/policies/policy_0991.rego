package risk.authorization.context.verify.policy_0991

# Auto-generated policy 991
# Package: risk.authorization.context.verify

# Metadata
metadata := {
    "policy_id": "0991",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0991 {
    data.policies.risk.enabled
}
allowed_0991 {
    input.user.role == "admin"
}
approved_0991 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default allowed_0991 = false

# Utility function for user info
