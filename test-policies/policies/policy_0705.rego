package compliance.validation.policy.deny.policy_0705

# Auto-generated policy 705
# Package: compliance.validation.policy.deny

# Metadata
metadata := {
    "policy_id": "0705",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0705 {
    input.user.active
    input.resource.public
}
denied_0705 {
    input.action == "delete"
    input.user.role != "admin"
}
approved_0705 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0705 {
    data.policies.compliance.enabled
}

# Utility function for user info
