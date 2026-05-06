package access.validation.resource.deny.policy_0265

# Auto-generated policy 265
# Package: access.validation.resource.deny

# Metadata
metadata := {
    "policy_id": "0265",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0265_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0265_allowed = false
policy_0265_denied if {
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
