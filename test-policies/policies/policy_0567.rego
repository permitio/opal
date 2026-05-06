package risk.enforcement.context.check.logic.policy_0567

# Auto-generated policy 567
# Package: risk.enforcement.context.check.logic

# Metadata
metadata := {
    "policy_id": "0567",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0567_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0567_allowed = false
policy_0567_allowed if {
    data.policies.risk.enabled
}
policy_0567_allowed if {
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
