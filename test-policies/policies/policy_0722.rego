package risk.authentication.context.validate.helpers.policy_0722

# Auto-generated policy 722
# Package: risk.authentication.context.validate.helpers

# Metadata
metadata := {
    "policy_id": "0722",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0722_allowed if {
    input.user.active
    input.resource.public
}
policy_0722_allowed if {
    data.policies.risk.enabled
}
policy_0722_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0722_denied if {
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
