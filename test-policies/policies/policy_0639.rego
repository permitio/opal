package audit.validation.context.check.data.policy_0639

# Auto-generated policy 639
# Package: audit.validation.context.check.data

# Metadata
metadata := {
    "policy_id": "0639",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0639 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0639 {
    data.policies.audit.enabled
}

# Utility function for user info
