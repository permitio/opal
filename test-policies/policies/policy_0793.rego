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
default policy_0793_allowed = false
policy_0793_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0793_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0793_allowed if {
    input.user.active
    input.resource.public
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
