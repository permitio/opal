package security.authentication.user.allow.utils.policy_0695

# Auto-generated policy 695
# Package: security.authentication.user.allow.utils

# Metadata
metadata := {
    "policy_id": "0695",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0695_allowed if {
    input.user.active
    input.resource.public
}
policy_0695_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0695_approved if {
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
