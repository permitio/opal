package compliance.enforcement.resource.deny.logic.policy_0813

# Auto-generated policy 813
# Package: compliance.enforcement.resource.deny.logic

# Metadata
metadata := {
    "policy_id": "0813",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0813 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0813 {
    data.policies.compliance.enabled
}
allowed_0813 {
    input.user.role == "admin"
}
allowed_0813 {
    input.user.active
    input.resource.public
}

# Utility function for user info
