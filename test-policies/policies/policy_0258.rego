package access.enforcement.context.validate.data.policy_0258

# Auto-generated policy 258
# Package: access.enforcement.context.validate.data

# Metadata
metadata := {
    "policy_id": "0258",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0258_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0258_allowed if {
    input.user.active
    input.resource.public
}
default policy_0258_allowed = false
policy_0258_denied if {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
