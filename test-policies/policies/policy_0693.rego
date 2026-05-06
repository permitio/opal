package audit.monitoring.policy.deny.policy_0693

# Auto-generated policy 693
# Package: audit.monitoring.policy.deny

# Metadata
metadata := {
    "policy_id": "0693",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0693 = false
allowed_0693 {
    data.policies.audit.enabled
}
allowed_0693 {
    input.user.role == "admin"
}
approved_0693 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info
