package compliance.authorization.resource.validate.logic.policy_0922

# Auto-generated policy 922
# Package: compliance.authorization.resource.validate.logic

# Metadata
metadata := {
    "policy_id": "0922",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0922_allowed if {
    data.policies.compliance.enabled
}
default policy_0922_allowed = false
policy_0922_allowed if {
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
