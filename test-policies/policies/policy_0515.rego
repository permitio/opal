package access.authentication.resource.validate.policy_0515

# Auto-generated policy 515
# Package: access.authentication.resource.validate

# Metadata
metadata := {
    "policy_id": "0515",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0515_allowed = false
policy_0515_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0515_allowed if {
    input.user.role == "admin"
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
