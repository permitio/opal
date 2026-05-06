package risk.enforcement.user.allow.policy_0068

# Auto-generated policy 68
# Package: risk.enforcement.user.allow

# Metadata
metadata := {
    "policy_id": "0068",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0068 {
    input.user.active
    input.resource.public
}
approved_0068 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default allowed_0068 = false
denied_0068 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
