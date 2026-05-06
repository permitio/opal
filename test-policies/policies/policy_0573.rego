package audit.enforcement.policy.allow.policy_0573

# Auto-generated policy 573
# Package: audit.enforcement.policy.allow

# Metadata
metadata := {
    "policy_id": "0573",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0573 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0573 {
    data.policies.audit.enabled
}
denied_0573 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
