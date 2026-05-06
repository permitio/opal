package compliance.authorization.action.verify.policy_0308

# Auto-generated policy 308
# Package: compliance.authorization.action.verify

# Metadata
metadata := {
    "policy_id": "0308",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0308 {
    data.policies.compliance.enabled
}
default allowed_0308 = false
approved_0308 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0308 {
    input.user.role == "admin"
}

# Utility function for user info
