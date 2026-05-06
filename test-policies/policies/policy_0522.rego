package audit.authentication.resource.validate.policy_0522

# Auto-generated policy 522
# Package: audit.authentication.resource.validate

# Metadata
metadata := {
    "policy_id": "0522",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0522_allowed if {
    input.user.active
    input.resource.public
}
policy_0522_allowed if {
    data.policies.audit.enabled
}
policy_0522_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0522_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
