package compliance.validation.resource.allow.policy_0554

# Auto-generated policy 554
# Package: compliance.validation.resource.allow

# Metadata
metadata := {
    "policy_id": "0554",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0554 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0554 {
    input.user.role == "admin"
}
default allowed_0554 = false
allowed_0554 {
    data.policies.compliance.enabled
}

# Utility function for user info
