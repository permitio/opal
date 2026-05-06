package audit.authorization.user.deny.policy_0572

# Auto-generated policy 572
# Package: audit.authorization.user.deny

# Metadata
metadata := {
    "policy_id": "0572",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0572 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0572 {
    input.user.role == "admin"
}
default allowed_0572 = false
allowed_0572 {
    data.policies.audit.enabled
}

# Utility function for user info
