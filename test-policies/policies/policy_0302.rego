package compliance.authorization.user.deny.policy_0302

# Auto-generated policy 302
# Package: compliance.authorization.user.deny

# Metadata
metadata := {
    "policy_id": "0302",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0302 {
    data.policies.compliance.enabled
}
denied_0302 {
    input.action == "delete"
    input.user.role != "admin"
}
approved_0302 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default allowed_0302 = false

# Utility function for user info
