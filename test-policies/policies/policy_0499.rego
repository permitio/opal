package compliance.monitoring.resource.allow.helpers.policy_0499

# Auto-generated policy 499
# Package: compliance.monitoring.resource.allow.helpers

# Metadata
metadata := {
    "policy_id": "0499",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0499 {
    input.user.active
    input.resource.public
}
approved_0499 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0499 {
    input.user.role == "admin"
}
allowed_0499 {
    data.policies.compliance.enabled
}

# Utility function for user info
