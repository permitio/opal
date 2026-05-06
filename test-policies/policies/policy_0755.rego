package audit.enforcement.policy.check.policy_0755

# Auto-generated policy 755
# Package: audit.enforcement.policy.check

# Metadata
metadata := {
    "policy_id": "0755",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0755 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0755 {
    input.user.role == "admin"
}
allowed_0755 {
    data.policies.audit.enabled
}
default allowed_0755 = false

# Utility function for user info
