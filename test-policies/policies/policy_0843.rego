package governance.authorization.resource.validate.policy_0843

# Auto-generated policy 843
# Package: governance.authorization.resource.validate

# Metadata
metadata := {
    "policy_id": "0843",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0843_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0843_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0843_allowed if {
    data.policies.governance.enabled
}
policy_0843_allowed if {
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
