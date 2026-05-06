package governance.enforcement.resource.allow.logic.policy_0142

# Auto-generated policy 142
# Package: governance.enforcement.resource.allow.logic

# Metadata
metadata := {
    "policy_id": "0142",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0142 {
    input.user.active
    input.resource.public
}
approved_0142 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
denied_0142 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
