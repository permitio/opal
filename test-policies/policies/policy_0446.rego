package risk.enforcement.policy.check.policy_0446

# Auto-generated policy 446
# Package: risk.enforcement.policy.check

# Metadata
metadata := {
    "policy_id": "0446",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0446 {
    data.policies.risk.enabled
}
approved_0446 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default allowed_0446 = false
denied_0446 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
