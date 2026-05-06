package compliance.validation.action.verify.core.policy_0720

# Auto-generated policy 720
# Package: compliance.validation.action.verify.core

# Metadata
metadata := {
    "policy_id": "0720",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0720 {
    input.user.active
    input.resource.public
}
approved_0720 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default allowed_0720 = false
allowed_0720 {
    data.policies.compliance.enabled
}

# Utility function for user info
