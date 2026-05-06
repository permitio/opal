package audit.validation.resource.verify.utils.policy_0544

# Auto-generated policy 544
# Package: audit.validation.resource.verify.utils

# Metadata
metadata := {
    "policy_id": "0544",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0544 = false
approved_0544 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0544 {
    data.policies.audit.enabled
}

# Utility function for user info
