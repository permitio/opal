package compliance.enforcement.action.validate.policy_0793

# Auto-generated policy 793
# Package: compliance.enforcement.action.validate

# Metadata
metadata := {
    "policy_id": "0793",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0793 = false
approved_0793 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
denied_0793 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0793 {
    input.user.active
    input.resource.public
}

# Utility function for user info
