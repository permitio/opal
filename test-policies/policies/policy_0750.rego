package audit.authentication.policy.deny.utils.policy_0750

# Auto-generated policy 750
# Package: audit.authentication.policy.deny.utils

# Metadata
metadata := {
    "policy_id": "0750",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0750 {
    data.policies.audit.enabled
}
approved_0750 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info
