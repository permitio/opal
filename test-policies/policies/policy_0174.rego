package risk.enforcement.context.allow.core.policy_0174

# Auto-generated policy 174
# Package: risk.enforcement.context.allow.core

# Metadata
metadata := {
    "policy_id": "0174",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0174_allowed if {
    data.policies.risk.enabled
}
policy_0174_allowed if {
    input.user.active
    input.resource.public
}
policy_0174_allowed if {
    input.user.role == "admin"
}
policy_0174_approved if {
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
