package security.authorization.resource.check.policy_0776

# Auto-generated policy 776
# Package: security.authorization.resource.check

# Metadata
metadata := {
    "policy_id": "0776",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0776 {
    data.policies.security.enabled
}
allowed_0776 {
    input.user.role == "admin"
}
approved_0776 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info
