package audit.enforcement.context.check.policy_0137

# Auto-generated policy 137
# Package: audit.enforcement.context.check

# Metadata
metadata := {
    "policy_id": "0137",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0137_allowed = false
policy_0137_allowed if {
    input.user.role == "admin"
}
policy_0137_allowed if {
    input.user.active
    input.resource.public
}
policy_0137_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
