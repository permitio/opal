package access.enforcement.context.allow.helpers.policy_0404

# Auto-generated policy 404
# Package: access.enforcement.context.allow.helpers

# Metadata
metadata := {
    "policy_id": "0404",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0404_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0404_approved if {
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
