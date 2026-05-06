package security.validation.resource.check.helpers.policy_0278

# Auto-generated policy 278
# Package: security.validation.resource.check.helpers

# Metadata
metadata := {
    "policy_id": "0278",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0278_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0278_allowed if {
    input.user.role == "admin"
}
policy_0278_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0278_allowed if {
    data.policies.security.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
