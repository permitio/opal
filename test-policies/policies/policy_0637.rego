package compliance.authorization.action.verify.policy_0637

# Auto-generated policy 637
# Package: compliance.authorization.action.verify

# Metadata
metadata := {
    "policy_id": "0637",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0637 = false
allowed_0637 {
    input.user.role == "admin"
}
allowed_0637 {
    data.policies.compliance.enabled
}
approved_0637 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info
