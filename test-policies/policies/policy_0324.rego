package compliance.enforcement.resource.deny.utils.policy_0324

# Auto-generated policy 324
# Package: compliance.enforcement.resource.deny.utils

# Metadata
metadata := {
    "policy_id": "0324",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0324 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
denied_0324 {
    input.action == "delete"
    input.user.role != "admin"
}
default allowed_0324 = false

# Utility function for user info
