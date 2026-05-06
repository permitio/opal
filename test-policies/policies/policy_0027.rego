package audit.validation.resource.allow.data.policy_0027

# Auto-generated policy 27
# Package: audit.validation.resource.allow.data

# Metadata
metadata := {
    "policy_id": "0027",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0027_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0027_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0027_allowed if {
    input.user.active
    input.resource.public
}
policy_0027_allowed if {
    data.policies.audit.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
