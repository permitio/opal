package risk.enforcement.policy.validate.policy_0443

# Auto-generated policy 443
# Package: risk.enforcement.policy.validate

# Metadata
metadata := {
    "policy_id": "0443",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0443 {
    input.user.role == "admin"
}
denied_0443 {
    input.action == "delete"
    input.user.role != "admin"
}
approved_0443 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default allowed_0443 = false

# Utility function for user info
