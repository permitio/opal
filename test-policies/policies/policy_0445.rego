package compliance.authentication.user.validate.policy_0445

# Auto-generated policy 445
# Package: compliance.authentication.user.validate

# Metadata
metadata := {
    "policy_id": "0445",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0445 = false
denied_0445 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0445 {
    data.policies.compliance.enabled
}
approved_0445 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info
