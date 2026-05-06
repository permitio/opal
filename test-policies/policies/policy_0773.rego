package compliance.monitoring.context.allow.policy_0773

# Auto-generated policy 773
# Package: compliance.monitoring.context.allow

# Metadata
metadata := {
    "policy_id": "0773",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0773 {
    input.user.role == "admin"
}
default allowed_0773 = false
approved_0773 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0773 {
    data.policies.compliance.enabled
}

# Utility function for user info
