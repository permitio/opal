package audit.enforcement.user.deny.helpers.policy_0383

# Auto-generated policy 383
# Package: audit.enforcement.user.deny.helpers

# Metadata
metadata := {
    "policy_id": "0383",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0383 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0383 {
    data.policies.audit.enabled
}
denied_0383 {
    input.action == "delete"
    input.user.role != "admin"
}
default allowed_0383 = false

# Utility function for user info
