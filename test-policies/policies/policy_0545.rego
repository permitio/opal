package compliance.validation.resource.verify.utils.policy_0545

# Auto-generated policy 545
# Package: compliance.validation.resource.verify.utils

# Metadata
metadata := {
    "policy_id": "0545",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0545 {
    data.policies.compliance.enabled
}
approved_0545 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0545 {
    input.user.role == "admin"
}
default allowed_0545 = false

# Utility function for user info
