package governance.enforcement.user.allow.policy_0733

# Auto-generated policy 733
# Package: governance.enforcement.user.allow

# Metadata
metadata := {
    "policy_id": "0733",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0733 {
    data.policies.governance.enabled
}
allowed_0733 {
    input.user.role == "admin"
}
approved_0733 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
denied_0733 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
