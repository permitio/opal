package compliance.validation.policy.deny.utils.policy_0002

# Auto-generated policy 2
# Package: compliance.validation.policy.deny.utils

# Metadata
metadata := {
    "policy_id": "0002",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0002 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0002 {
    data.policies.compliance.enabled
}
approved_0002 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info
