package audit.authorization.resource.allow.policy_0712

# Auto-generated policy 712
# Package: audit.authorization.resource.allow

# Metadata
metadata := {
    "policy_id": "0712",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0712 {
    input.user.active
    input.resource.public
}
approved_0712 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
denied_0712 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
