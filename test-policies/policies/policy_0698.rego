package risk.enforcement.action.verify.policy_0698

# Auto-generated policy 698
# Package: risk.enforcement.action.verify

# Metadata
metadata := {
    "policy_id": "0698",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0698 {
    data.policies.risk.enabled
}
denied_0698 {
    input.action == "delete"
    input.user.role != "admin"
}
approved_0698 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default allowed_0698 = false

# Utility function for user info
