package compliance.validation.resource.allow.policy_0906

# Auto-generated policy 906
# Package: compliance.validation.resource.allow

# Metadata
metadata := {
    "policy_id": "0906",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0906 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
denied_0906 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0906 {
    data.policies.compliance.enabled
}

# Utility function for user info
